import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import numpy as np
import math
import geopandas as gpd
from shapely.geometry import Polygon, Point
from branca.colormap import LinearColormap
from geopy.geocoders import Nominatim

# Настройки страницы - минимальный интерфейс
st.set_page_config(layout="wide", page_title="Экологическая карта рисков")
st.title("🌐 Карта экологических рисков")

# Уменьшаем верхние отступы
st.markdown("""
<style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
    }
    .stDataFrame {
        max-height: 300px;
        overflow-y: auto;
    }
</style>
""", unsafe_allow_html=True)

# Инициализация состояния сессии
if 'center_point' not in st.session_state:
    st.session_state.center_point = [59.954, 30.306]  # Центр СПб
if 'address' not in st.session_state:
    st.session_state.address = "Кронверкский проспект 49"
if 'precalculated_grid' not in st.session_state:
    st.session_state.precalculated_grid = None


# Загрузка данных
@st.cache_data
def load_data():
    demo_data = {
        'name': [
            'Химический завод "Нева"',
            'Мусоросжигательный завод №4',
            'ТЭЦ-2',
            'Полигон ТБО "Северный"',
            'Нефтебаза "Восточная"',
            'Автомагистраль КАД',
            'Порт "Большой порт Санкт-Петербург"',
            'Аэропорт Пулково'
        ],
        'lat': [59.985, 59.870, 59.935, 59.920, 59.910, 59.900, 59.880, 59.800],
        'lon': [30.300, 30.480, 30.350, 30.230, 30.200, 30.400, 30.220, 30.260],
        'pollution_level': [9.5, 9.0, 8.5, 8.5, 8.0, 7.5, 7.0, 7.5],
        'danger_level': ['Критический', 'Критический', 'Высокий', 'Высокий', 'Высокий', 'Высокий', 'Высокий',
                         'Высокий'],
        'object_type': [
            'Химический завод',
            'Мусоросжигательный завод',
            'Теплоэлектроцентраль',
            'Полигон ТБО',
            'Нефтебаза',
            'Автомагистраль',
            'Порт',
            'Аэропорт'
        ]
    }
    return pd.DataFrame(demo_data)


# Создание сетки для всего города
def create_full_grid():
    min_lat, max_lat = 59.80, 60.05
    min_lon, max_lon = 30.10, 30.70
    cell_size = 0.0045

    lats = np.arange(min_lat, max_lat, cell_size)
    lons = np.arange(min_lon, max_lon, cell_size)

    grid = []
    for i in range(len(lats) - 1):
        for j in range(len(lons) - 1):
            poly = Polygon([
                (lons[j], lats[i]),
                (lons[j + 1], lats[i]),
                (lons[j + 1], lats[i + 1]),
                (lons[j], lats[i + 1]),
                (lons[j], lats[i])
            ])
            grid.append({
                'geometry': poly,
                'left': lons[j],
                'right': lons[j + 1],
                'bottom': lats[i],
                'top': lats[i + 1]
            })
    return gpd.GeoDataFrame(grid, crs="EPSG:4326")


# Расчет уровня риска
def calculate_full_risk_grid(grid, sources):
    type_weights = {
        'Химический завод': 1.8,
        'Мусоросжигательный завод': 1.7,
        'Теплоэлектроцентраль': 1.4,
        'Полигон ТБО': 1.6,
        'Нефтебаза': 1.5,
        'Автомагистраль': 1.2,
        'Порт': 1.3,
        'Аэропорт': 1.4
    }

    risks = []
    for idx, cell in grid.iterrows():
        cell_center = cell['geometry'].centroid
        total_risk = 0

        for _, source in sources.iterrows():
            distance = haversine_distance(
                cell_center.y, cell_center.x,
                source['lat'], source['lon']
            )
            weight = type_weights.get(source['object_type'], 1.0)
            risk = source['pollution_level'] * weight / (1 + distance / 500)
            total_risk += risk

        risks.append(total_risk)

    max_risk = max(risks) if risks else 1
    grid['risk_level'] = [r / max_risk * 10 for r in risks]
    return grid


# Расчет расстояния
def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


# Геокодирование адреса
def geocode_address(address):
    geolocator = Nominatim(user_agent="eco_risk_map")
    try:
        location = geolocator.geocode(address + ", Санкт-Петербург")
        if location:
            return [location.latitude, location.longitude]
    except:
        pass
    return None


# Иконки для объектов
def get_icon_for_type(obj_type):
    icons = {
        'Химический завод': 'industry',
        'Мусоросжигательный завод': 'fire',
        'Теплоэлектроцентраль': 'bolt',
        'Полигон ТБО': 'trash',
        'Нефтебаза': 'oil-can',
        'Автомагистраль': 'road',
        'Порт': 'ship',
        'Аэропорт': 'plane'
    }
    return icons.get(obj_type, 'circle')


# Создание карты с фокусом на визуализацию
def create_risk_map(grid, sources, center, radius=2000):
    m = folium.Map(location=center, zoom_start=13,
                   tiles='CartoDB positron',
                   control_scale=True,
                   width='100%',
                   height='100%')

    colormap = LinearColormap(['#00ff00', '#ffff00', '#ff0000'], vmin=0, vmax=10)

    # Упрощенная сетка с повышенной прозрачностью
    for idx, row in grid.iterrows():
        cell_center = Point((row['left'] + row['right']) / 2, (row['bottom'] + row['top']) / 2)
        distance = haversine_distance(
            center[0], center[1],
            cell_center.y, cell_center.x
        )

        if distance <= radius and row['risk_level'] > 0.1:
            folium.Polygon(
                locations=[
                    [row['bottom'], row['left']],
                    [row['bottom'], row['right']],
                    [row['top'], row['right']],
                    [row['top'], row['left']],
                    [row['bottom'], row['left']]
                ],
                color=colormap(row['risk_level']),
                fill=True,
                fill_opacity=0.5,  # Увеличиваем прозрачность
                weight=0.3,  # Тонкие границы
                tooltip=f"Риск: {row['risk_level']:.2f}"
            ).add_to(m)

    # Упрощенные маркеры
    for _, source in sources.iterrows():
        icon_name = get_icon_for_type(source['object_type'])
        folium.Marker(
            [source['lat'], source['lon']],
            popup=f"<b>{source['name']}</b>",
            icon=folium.Icon(color='black', icon=icon_name, prefix='fa')
        ).add_to(m)

    # Центральный маркер
    folium.Marker(
        center,
        popup="Центр анализа",
        icon=folium.Icon(color='blue', icon='star', prefix='fa')
    ).add_to(m)

    # Область анализа
    folium.Circle(
        location=center,
        radius=radius,
        color='#0066cc',
        fill=True,
        fill_opacity=0.1,
        weight=1
    ).add_to(m)

    colormap.add_to(m)
    return m


# Основной интерфейс
data = load_data()

# Компактный сайдбар
with st.sidebar:
    st.header("Управление")

    # Загрузка данных
    uploaded_file = st.file_uploader("Загрузить данные", type="csv")
    if uploaded_file:
        user_data = pd.read_csv(uploaded_file)
        st.success(f"Загружено {len(user_data)} объектов!")
        data = user_data

    # Поиск по адресу
    new_address = st.text_input("Адрес поиска:", st.session_state.address)
    search_radius = st.slider("Радиус анализа (м):", 500, 5000, 2000)

    if st.button("Показать на карте"):
        new_center = geocode_address(new_address)
        if new_center:
            st.session_state.center_point = new_center
            st.session_state.address = new_address
            st.success("Адрес найден!")
        else:
            st.error("Адрес не найден!")

# Предварительный расчет сетки
if st.session_state.precalculated_grid is None:
    with st.spinner('Идет расчет карты рисков...'):
        full_grid = create_full_grid()
        st.session_state.precalculated_grid = calculate_full_risk_grid(full_grid, data)

# Основной контент - только карта
if st.session_state.precalculated_grid is not None:
    # Используем весь доступный экран
    st_folium(
        create_risk_map(
            st.session_state.precalculated_grid,
            data,
            st.session_state.center_point,
            radius=search_radius
        ),
        width=1600,
        height=800,
        key="map"
    )
else:
    st.warning("Завершаем расчеты...")

# Минималистичная легенда
st.caption("""
**Легенда:** 
<span style="color:green">Низкий риск</span> | 
<span style="color:yellow">Средний риск</span> | 
<span style="color:red">Высокий риск</span> | 
<i class="fa fa-star"></i> Центр анализа
""")

# Подключаем FontAwesome
st.markdown("""
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
""", unsafe_allow_html=True)

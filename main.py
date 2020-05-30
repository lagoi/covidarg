import pandas as pd
import numpy as np
import geopandas as gpd
import json
from shapely.geometry import Polygon, MultiPolygon
from bokeh.io import show, output_file
from bokeh.io.doc import curdoc
from bokeh.models import HoverTool, Paragraph, Div, ColumnDataSource, Tabs, Panel, Select, CheckboxButtonGroup, GeoJSONDataSource, LinearColorMapper, ColorBar, NumeralTickFormatter, DatetimeTickFormatter
from bokeh.plotting import figure
from bokeh.palettes import Spectral11, brewer
from bokeh.layouts import layout

###### Extract Data ######

# Data ref: https://www.argentina.gob.ar/coronavirus/informe-diario/abril2020
data = pd.read_csv('datoscovid.txt', sep = "\t", header = "infer", index_col="Distrito", thousands='.')
#Correccion de mal formateo de los datos y compatibilidad con el mapa del ign
data = data.rename(index={'Ciudad de Buenos Aires': 'Ciudad Autónoma de Buenos Aires', 
    'Tierra del Fuego': 'Tierra del Fuego, Antártida e Islas del Atlántico Sur',
    "Catamarca 0 0 0 0": "Catamarca",
    "Formosa 0 0 0 0": "Formosa"
    })
data = data.assign(nam=data.index)
data = data.fillna(0)


# Mapa de argentina con division interprovincial del IGN
arg = gpd.read_file("data/provincia.shp", projection="GEOGCS['GCS_WGS_1984',DATUM['D_WGS_1984',SPHEROID['WGS_1984',6378137,298.257223563]],PRIMEM['Greenwich',0],UNIT['Degree',0.017453292519943295]]")

# Union de datos coronavirus con mapa
arg = pd.merge(arg, data, on="nam")

# Quitar todos los poligonos de la antartida y las islas del atlantico sur por motivos visuales 
# y que son de poca relevancia para el caso de estudio
points = [(-80.0, -58.0), (-55.0, -58.0), (-55.0,-50.0), (-20.0,-50.0), (-20.0, -90.0), (-80.0, -90.0)]
antartida_e_islas = gpd.GeoSeries(Polygon(points))
new_poligon_list = []
for multipolygon in arg[arg.nam=='Tierra del Fuego, Antártida e Islas del Atlántico Sur'].geometry:
    for polygon in multipolygon:
        if not any(gpd.GeoSeries(polygon).intersects(antartida_e_islas)):
            new_poligon_list.append(polygon)

arg.geometry[16] = MultiPolygon(new_poligon_list)

# Reducir la cantidad de puntos en el mapa para reducir el tiempo de carga
for i in range(arg.shape[0]):
    arg.geometry[i] = arg.geometry[i].simplify(tolerance=0.05, preserve_topology=False)


casos_arg = pd.read_csv('casosarg.csv', sep = ",", header = 0, names=("dias","casos"))
casos_arg['dias'] = pd.date_range('3/6/2020', periods=casos_arg.shape[0], freq='D')

casos_arg_predict = pd.read_csv('predict5.csv', sep = ",", header = 0, names=("dias","casos"))
casos_arg_predict['dias'] = pd.date_range(casos_arg['dias'][casos_arg.shape[0]-1]+pd.Timedelta('1d'), periods=casos_arg_predict.shape[0], freq='D')

mayores_65 = pd.read_csv("data/mayores65.txt", sep = ",")
arg = pd.merge(arg, mayores_65, on="nam")

centros = pd.read_csv("data/centros.txt", sep = ",")
arg = pd.merge(arg, centros, on="nam")

###### Bokeh ######

def tabMapWithSelectAndUpdate(arg: pd.DataFrame):
    arg['Confirmados2'] = arg['Confirmados']/1000
    arg['Recuperados2'] = arg['Recuperados']/1000
    arg['Fallecidos2'] = arg['Fallecidos']/1000
    arg['Activos2'] = arg['Activos']/1000
    arg['Mayores_de_652'] = arg['Mayores_de_65']/1000000
    
    
    merged_json = json.loads(arg.to_json())
    json_data = json.dumps(merged_json)

    # Input geojson source that contains features for plotting:
    geosource = GeoJSONDataSource(geojson = json_data)

    # Make a selection object: select
    select1 = Select(title='Dato en Color:', value='Casos Confirmados', options=['Casos Confirmados',
                                                                               'Recuperados',
                                                                               'Fallecidos', 
                                                                               'Activos',
                                                                               'Mayores de 65'])

    select2 = CheckboxButtonGroup(active=[1], labels=['Casos Confirmados',
                                                                               'Recuperados',
                                                                               'Fallecidos', 
                                                                               'Activos',
                                                                               'Mayores de 65'])

    def update_plot(attr, old, new):    
        # The input cr is the criteria selected from the select box
        cr1 = select1.value
        cr2 = select2.active
        fields = {  'Casos Confirmados': 'Confirmados',
                'Recuperados': 'Recuperados',
                'Fallecidos': 'Fallecidos', 
                'Activos': 'Activos',
                'Mayores de 65': 'Mayores_de_65'
                }
        fields2 = ['Confirmados2','Recuperados2','Fallecidos2', 'Activos2', 'Mayores_de_652']
        input_field1 = fields[cr1]
        input_fields2 = [fields2[index] for index in cr2]
    
        map_arg = make_map(input_field1, input_fields2)
        l.children.pop()
        l.children.append(map_arg)


    # Create a plotting function
    def make_map(field_name1, field_names2):    
        # Set the format of the colorbar
        min_range = 0
        max_range = max(arg[field_name1])
        field_format = "0"

        if field_name1 == "Confirmados":
            # Define a sequential multi-hue color palette.
            palette = brewer['Blues'][8]
            # Reverse color order so that dark blue is highest.
            palette = palette[::-1]
        elif field_name1 == "Recuperados":
            palette = brewer['Greens'][8]
            palette = palette[::-1]
        elif field_name1 == "Fallecidos":
            palette = brewer['Reds'][8]
            palette = palette[::-1]
        else:
            palette = brewer['Blues'][8]
            palette = palette[::-1]


        # Instantiate LinearColorMapper that linearly maps numbers in a range, into a sequence of colors.
        color_mapper = LinearColorMapper(palette = palette, low = min_range, high = max_range)

        # Create color bar.
        format_tick = NumeralTickFormatter(format=field_format)
        color_bar = ColorBar(color_mapper=color_mapper, label_standoff=18, formatter=format_tick,
        border_line_color=None, location = (0, 0))

        # Create figure object.

        map_arg = figure(title = field_name1, 
            plot_height = 900, plot_width = 700,)
        map_arg.xgrid.grid_line_color = None
        map_arg.ygrid.grid_line_color = None
        map_arg.axis.visible = False

        # Add patch renderer to figure. 
        patches = map_arg.patches('xs','ys', source = geosource, fill_color = {'field' : field_name1, 'transform' : color_mapper},
            line_color = 'black', line_width = 0.25, fill_alpha = 1)
        
        #Add circles renderer to figure.
        for field_name2 in field_names2:
            if field_name2 == "Confirmados2":
                color='#0000ff'
            elif field_name2 == "Recuperados2":
                color='#00ff00'
            elif field_name2 == "Fallecidos2":
                color='#ff0000'
            elif field_name2 == "Activos2":
                color='#ffff00'
            else:
                color='#000000'
            map_arg.circle("lon","lat",source=geosource, fill_alpha=0.5, fill_color = color,
                        line_color="#FFFFFF", line_width=2, line_alpha=0.5,radius=field_name2)

        # Specify color bar layout.
        map_arg.add_layout(color_bar, 'right')

        # Add hover tool
        hover_map = HoverTool(tooltips = """
                                    <div class="plot-tooltip">
                                        <div>
                                            <h5>@nam</h5>
                                        </div>
                                        <div>
                                            <span style="font-weight: bold;">Casos Confirmados: </span>@Confirmados
                                        </div>
                                        <div>
                                            <span style="font-weight: bold;">Recuperados: </span>@Recuperados
                                        </div>
                                        <div>
                                            <span style="font-weight: bold;">Fallecidos: </span>@Fallecidos
                                        </div>
                                        <div>
                                            <span style="font-weight: bold;">Activos: </span>@Activos
                                        </div>
                                        <div>
                                            <span style="font-weight: bold;">Habitantes Mayores de 65: </span>@Mayores_de_65
                                        </div>
                                    </div>
                                    """,
                               renderers=[patches])
        # Add the hover tool to the graph
        map_arg.add_tools(hover_map)
        return map_arg

    # Attach function to select
    select1.on_change('value', update_plot)
    select2.on_change('active', update_plot)

    # Call the plotting function
    map_arg = make_map('Confirmados', ['Recuperados2'])

    paragraph1 = Paragraph(text="""Datos en circulos:""",
        width=600)

    l = layout([    [select1],
                    [paragraph1],
                    [select2],
                    [map_arg]
                ]) 
    tab = Panel(child=l,title="Mapa Actual",name='mapa_actual')
    return tab



def tabCasosXDia(casos_arg: pd.DataFrame, casos_arg_predict: pd.DataFrame):

    casos_nuevos = [casos_arg["casos"][0]]
    for i in range(1,casos_arg.shape[0]):
        casos_nuevos.append(casos_arg["casos"][i]-casos_arg["casos"][i-1])

    casos_arg["casos_z1"] = casos_nuevos

    casos_nuevos = [casos_arg_predict["casos"][0]-casos_arg["casos"][casos_arg.shape[0]-1]]
    for i in range(1,casos_arg_predict.shape[0]):
        casos_nuevos.append(casos_arg_predict["casos"][i]-casos_arg_predict["casos"][i-1])
    casos_arg_predict["casos_z2"] = casos_nuevos

    casos = pd.merge(casos_arg, casos_arg_predict, on="dias", how="outer")
    

    # Grafico casos por dia
    casos_arg_ds = ColumnDataSource(casos)
    casos_dia = figure(plot_width = 900, plot_height = 500, 
                title = 'Casos de Coronavirus por dia en Argentina',
                x_axis_label = 'Dia', y_axis_label = 'Casos', x_axis_type="datetime")
    

    gliph1 = casos_dia.line('dias','casos_x',source=casos_arg_ds, legend_label='Casos Confirmados', color='red', line_width=3)
    casos_dia.line('dias','casos_z1',source=casos_arg_ds, legend_label='Casos Nuevos', color='gold', line_width=3)    
    gliph2 = casos_dia.line('dias','casos_y',source=casos_arg_ds, legend_label='Casos Predichos', color='blue', line_width=3)
    casos_dia.line('dias','casos_z2',source=casos_arg_ds, legend_label='Casos Nuevos Predichos', color='green', line_width=3)

    casos_dia.legend.location="top_left"

    hover1 = HoverTool(  tooltips = """ 
                                    <div class="plot-tooltip">
                                        <div>
                                            <h5>@dias{%d-%B-%Y}</h5>
                                        </div>
                                        <div>
                                            <span style="font-weight: bold;">Casos Confirmados: </span>@casos_x
                                        </div>
                                        <div>
                                            <span style="font-weight: bold;">Casos Nuevos: </span>@casos_z1
                                        </div>
                                    </div>
                                    """,
                        mode='vline',
                        formatters={'@dias': 'datetime'},
                        renderers = [gliph1])
    hover2 = HoverTool(  tooltips = """ 
                                    <div class="plot-tooltip">
                                        <div>
                                            <h5>@dias{%d-%B-%Y}</h5>
                                        </div>
                                        <div>
                                            <span style="font-weight: bold;">Casos Confirmados: </span>@casos_y
                                        </div>
                                        <div>
                                            <span style="font-weight: bold;">Casos Nuevos: </span>@casos_z2
                                        </div>
                                    </div>
                                    """,
                        mode='vline',
                        formatters={'@dias': 'datetime'},
                        renderers = [gliph2])
    casos_dia.add_tools(hover1, hover2)

    casos_dia.xaxis.formatter = DatetimeTickFormatter(days="%d-%B-%Y")

    # Create Tab
    l = layout( [[casos_dia]])
    tab = Panel(child=l, title = 'Evolucion Diaria', name='evolucion_diaria')
    return tab





tab_list = []
tab_list.append(tabCasosXDia(casos_arg, casos_arg_predict))
tab_list.append(tabMapWithSelectAndUpdate(arg))

tabs = Tabs(tabs=tab_list, name='tabs')

curdoc().add_root(tabs)
curdoc().title = "Covid Argentina"
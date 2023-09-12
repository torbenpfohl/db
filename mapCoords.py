"""
show the stations on a map
"""

import sqlite3
import os
from shapely.geometry import Point
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt

class Map:
  stationsDbPath = os.getcwd()+os.sep+"stations"+os.sep+"stations.db"

  def __init__(self):
    self.paint()

  def getFromDb(self):
    con = sqlite3.connect(self.stationsDbPath)
    cur = con.cursor()
    res = cur.execute("SELECT * from stations limit 10")
    content = res.fetchall()
    stationNames = list()
    stationIds = list()
    lats = list()
    lngs = list()
    for name, id, lat, lng in content:
      stationNames.append(name)
      stationIds.append(id)
      lats.append(lat)
      lngs.append(lng)
    df = pd.DataFrame(
      {
        "Station": stationNames,
        "Id": stationIds,
        "Lat": lats,
        "Lng": lngs
      }
    )
    return df
  
  def paint(self):
    df = self.getFromDb()
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.Lng, df.Lat), crs="EPSG:4326")
    print(gdf.head())
    world = gpd.read_file(gpd.datasets.get_path("naturalearth_lowres"))
    #ax = world.clip([4,44,17,57]).plot()
    #gdf.plot(ax=ax, color="red")
    # plt.show(block=True)
    gdf.plot(ax=world.clip([4,44,17,57]).plot(), marker=".", color="black", markersize=2)
    plt.savefig("map")

if __name__ == "__main__":
  map = Map()
    

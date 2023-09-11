"""
Stationen speichern und aktuell halten
"""

# https://reiseauskunft.bahn.de/bin/ajax-getstop.exe/dn?
# 
# REQ0JourneyStopsS0A=1&REQ0JourneyStopsF=excludeMetaStations&REQ0JourneyStopsS0G=darm%3F&js=true&=

# https://reiseauskunft.bahn.de/bin/bhftafel.exe/dn?ld=4359&protocol=https:&rt=1&showBhfInfo=yes&evaId="+evaId+"&info=yes&rtMode=&

# https://reiseauskunft.bahn.de/bin/bhftafel.exe/dn?ld=4359&protocol=https:&evaId=8000068

import requests
from bs4 import BeautifulSoup

class StationManagement:
  def __init__(self):
    self.baseUrl = "https://reiseauskunft.bahn.de/bin/bhftafel.exe/dn?ld=4359&protocol=https:&evaId="
    self.internalList = list()  # [(stationName, stationId)]
    self.exportList = list()  # [stationName]

  def createStationsList(self):
    """
    stations need to replace " " with "+" for the request
    """
    id = 1
    while True:
      stationName, stationId = self.getStationName(id)
      if not stationId:
        print("all stations registered.")
        print("last station id:", id-1)
        break
      self.internalList.append((stationName, stationId))
      self.exportList(stationName)
      id += 1

  def getStationName(self, id):
    """
    returns stationName and -number
    or returns ("error", 0) on error
    """
    evaId = 8000000 + id
    url = self.baseUrl + str("000720001")
    response = requests.get(url)
    parsedHtml = BeautifulSoup(response.text, "html.parser")
    station = parsedHtml.find("label", {"for": "HFS_input"}).next_sibling
    stationName = "".join(station.stripped_strings)
    print(stationName)
    if stationName:
      return (stationName, id)
    else:
      return ("error", 0)

if __name__ == "__main__":
  test = StationManagement()
  test.getStationName(68)
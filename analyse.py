## download data and get value and extId data

"""
IDEA 1:
spread the requests out:
start a "database" of already requested strings
and a "database" of recieved stations

logic:
- build requests with a kind of bruteforce logic (a, b, c, ..., "aa", "ab", ...)
  also include " " (space)
- extract relevant infos (stationName, stationId, stationCords) 
  (might just save everything)
- check with the id as a key, if the station is already present in the database
  and put it in if not.

- extra but important: 
  put a limit on the requests for a certain time. 
  programm should be stopable.
  put a (random) timebuffer between requests

IDEA 2:
same idea of spreading the requests.
but now build them with the id starting with 000000000 and increment


"""

import requests
import json
import string
import os
import xml.etree.ElementTree as ET
import sqlite3
import html

class DatabaseBuilder:
  # results can also include stations in other countries, so i need to 
  # reverse geocode as well.
  # use multiple services (rate limited free version available)
  # https://www.geonames.org/findNearbyPlaceName?lat=49.875803&lng=8.647740
  # https://nominatim.openstreetmap.org/search.php?q=49.875803%2C+8.647740&format=jsonv2
  # + more
  def __init__(self):
    self.partialCities = list()
    self.run()

  def startup(self):
    # load last requested partial city
    partialStations = "partialCities.txt"
    currentDir = os.getcwd()
    targetDir = currentDir + os.sep + "stations"
    if "stations" not in os.listdir(currentDir):
      os.mkdir("stations")
    if partialStations not in os.listdir(targetDir):
      open(targetDir+os.sep+partialStations, "a").close()
    with open(targetDir+os.sep+partialStations, "rb") as f:
      try:
        f.seek(-2, 2)
        while f.read(1) != b"\n":
          f.seek(-2, 1)
      except:
        f.seek(0)
      lastLine = f.readline().decode(encoding="utf-8").removesuffix("\n")
    if lastLine == "":
      lastPartialCity = ""
    else:
      lastPartialCity = lastLine
    return lastPartialCity
    
  def close(self):
    # save the partialCities list to file (append)
    print(self.partialCities)
    partialCitiesFile = os.getcwd() + os.sep + "stations" + os.sep + "partialCities.txt"
    s = "\n".join(self.partialCities) + "\n"
    with open(partialCitiesFile, "a", encoding="utf-8") as file:
      file.write(s)

  def run(self):
    requestCounter = 0
    lastPartialCity = self.startup()
    partialCity = self.nextPartialCity(lastPartialCity)
    while requestCounter < 2:
      self.partialCities.append(partialCity)
      data = self.get(partialCity)
      formatedData = self.formatData(data)
      if len(formatedData) == 0:
        continue
      germanStations = self.verifyData(formatedData)
      if len(germanStations):
        self.storeData(germanStations)
      partialCity = self.nextPartialCity(partialCity)
      requestCounter += 1
    self.close()

  def nextPartialCity(self, lastPartialCity):
    letters = string.ascii_lowercase + " _"
    if lastPartialCity == "":
      return letters[0]
    nextPartialCity = ""
    flag = 0
    lastPartialCityReversed = "".join([i for i in reversed(lastPartialCity)])
    for index, letter in enumerate(lastPartialCityReversed):
      if letter == letters[-1]:
        nextPartialCity += letters[0]
        flag = 1
      else:
        nextPartialCity += letters[letters.find(letter) + 1] + lastPartialCityReversed[index+1:]
        flag = 0
        break
    if flag == 1:
      nextPartialCity = letters[0] + nextPartialCity
    nextPartialCity = "".join([i for i in reversed(nextPartialCity)])
    return nextPartialCity

  def get(self, partialCity):
    url = f"https://reiseauskunft.bahn.de/bin/ajax-getstop.exe/dn?REQ0JourneyStopsS0A=1&REQ0JourneyStopsF=excludeMetaStations&REQ0JourneyStopsS0G={partialCity}&js=true"
    response = requests.get(url)
    data = response.text
    if data.startswith("SLs.sls="):
      data = data.removeprefix("SLs.sls=")
    if data.endswith(";SLs.showSuggestion();"):
      data = data.removesuffix(";SLs.showSuggestion();")
    jData = json.loads(data)
    return jData

  def formatData(self, data):
    # einfache aufbereitung der erhaltenen daten
    stations = data["suggestions"]
    stationsNewFormat = list()
    for station in stations:
      stationName = html.unescape(station["value"])
      stationId = station["extId"]
      codedId = station["id"]
      lat = station["ycoord"]
      lat = lat[:-6] + "." + lat[-6:]
      lng = station["xcoord"]
      lng = lng[:-6] + "." + lng[-6:]
      stationNewFormat = {"stationName": stationName,
                          "stationId"  : stationId,
                          "lat"        : lat,
                          "lng"        : lng
                          }
      stationsNewFormat.append(stationNewFormat)
    return stationsNewFormat

  def verifyData(self, stations):
    # check geolocation (german station?)
    germanStations = list()
    for station in stations:
      lat = station["lat"]
      lng = station["lng"]
      url = f"https://www.geonames.org/findNearbyPlaceName?lat={lat}&lng={lng}"
      response = requests.get(url)
      root = ET.fromstring(response.text)
      countryCode = root[0].find("countryCode").text
      if countryCode == "DE":
        germanStations.append(station)
    return germanStations


  def storeData(self, stations):
    # check for duplicates and save into database
    # use sqlite as a start
    dbLocation = os.getcwd() + os.sep + "stations" + os.sep + "stations.db"
    con = sqlite3.connect(dbLocation)
    cur = con.cursor()
    columns = ",".join(stations[0].keys())
    columnCount = len(stations[0].keys())
    cur.execute(f"CREATE TABLE if not exists stations({columns})")
    res = cur.execute("SELECT stationId FROM stations")
    presentStationIds = res.fetchall()
    presentStationIds = [id[0] for id in presentStationIds]
    stationsForDb = list()
    for station in stations:
      if station["stationId"] not in presentStationIds:
        stationsForDb.append(tuple(station.values()))
    print(stationsForDb)
    if len(stationsForDb) > 0:
      placeHolders = ",".join(["?"] * columnCount)
      cur.executemany(f"INSERT INTO stations VALUES({placeHolders})", stationsForDb)
      con.commit()
    con.close()

class Analyse:
  def __init__(self, partialCity):
    data = self.get(partialCity)
    self.work(data)

  def get(self, partialCity):
    # partialCity = "darmst_"
    url = f"https://reiseauskunft.bahn.de/bin/ajax-getstop.exe/dn?REQ0JourneyStopsS0A=1&REQ0JourneyStopsF=excludeMetaStations&REQ0JourneyStopsS0G={partialCity}&js=true"
    response = requests.get(url)
    data = response.text
    if data.startswith("SLs.sls="):
      data = data.removeprefix("SLs.sls=")
    if data.endswith(";SLs.showSuggestion();"):
      data = data.removesuffix(";SLs.showSuggestion();")
    jData = json.loads(data)
    return jData

  def work(self, data):
    lData = data["suggestions"]
    namesAndIds = list()
    for row in lData:
      stationName = row["value"]
      stationId = row["extId"]
      namesAndIds.append([stationName, stationId])
    for station in namesAndIds:
      print(station)


if __name__ == "__main__":
  # for abc in string.ascii_lowercase:
    # analyse = Analyse(abc)
  db = DatabaseBuilder()
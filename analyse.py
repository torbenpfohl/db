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

NEW IDEA 3:
since now I have a nice big database, I can go from the stationIds and increment
and decrement this idea and do a request with it.
if I get an error (not valid station), I stop in this direction
still need to verify the station before inserting it into the database
extra:
  saving the last time I made a successful request to the station (to keep
  track of the active stations.)

"""

import requests
import json
import string
import os
import xml.etree.ElementTree as ET
import sqlite3
import html
import re
import reverse_geocode
import time
import random

class DatabaseBuilder:
  # results can also include stations in other countries, so i need to 
  # reverse geocode as well.
  # use multiple services (rate limited free version available)
  # https://www.geonames.org/findNearbyPlaceName?lat=49.875803&lng=8.647740
  # https://nominatim.openstreetmap.org/search.php?q=49.875803%2C+8.647740&format=jsonv2
  # + more
  stationsDbPath = os.getcwd()+os.sep+"stations"+os.sep+"stations.db"

  # try decorators/wrappers
  def wrapper(func):
    # TODO: fortschrittsanzeige für sleep-timer
    def inner(*args, **kwargs):
      while True:
        func(*args, **kwargs)
        rand = random.randint(60,120)
        print(f"sleeping time: {rand}")
        time.sleep(rand)
    return inner

  def __init__(self, buildWith):
    """
    buildWith : "city" or "id"
    """
    self.lastPartialRequests = list()
    if buildWith == "city":
      filename = "partialCities.txt"
      run = self.run
    elif buildWith == "id":
      filename = "lastStationId.txt"
      run = self.run2
    else:
      print("not a valid buildWith value: 'city' or 'id'")
      return
    
    self.dbConnect = sqlite3.connect(os.getcwd()+os.sep+"stations"+os.sep+"stations.db")
    try:
      run()
      self.dbConnect.close()
    except KeyboardInterrupt:
      self.lastPartialRequests.pop()
      self.close("stations", filename)
      self.dbConnect.close()
    except Exception as error:
      print(repr(error))
      self.lastPartialRequests.pop()
      self.close("stations", filename)
      self.dbConnect.close()

  def startup(self, foldername, filename):
    # load last requested partial city
    currentDir = os.getcwd()
    targetDir = currentDir + os.sep + foldername
    if foldername not in os.listdir(currentDir):
      os.mkdir(foldername)
    if filename not in os.listdir(targetDir):
      open(targetDir+os.sep+filename, "a").close()
      lastPartialCity = ""
    else:
      with open(targetDir+os.sep+filename, "rb") as f:
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
    
  def close(self, foldername, filename):
    # save the partialCities list to file (append)
    # TODO: next iteration: save them together with the number of suggestions
    #       they pulled (and also the number of stations they eventually logged into the db)
    print(self.lastPartialRequests[-1])
    partialCitiesFile = os.getcwd() + os.sep + foldername + os.sep + filename
    s = self.lastPartialRequests[-1] + "\n"
    with open(partialCitiesFile, "w", encoding="utf-8") as file:
      file.write(s)
    # print the count of already logged stations
    con = sqlite3.connect(self.stationsDbPath)
    count = con.execute("select count(stationId) from stations").fetchall()
    print(count)
  
  @wrapper
  def run(self):
    requestCounter = 0
    lastPartialCity = self.startup("stations", "partialCities.txt")
    partialCity = self.nextPartialCity(lastPartialCity)
    while requestCounter < 100:
      self.lastPartialRequests.append(partialCity)
      data = self.get(partialCity)
      formatedData = self.formatData(data)
      if len(formatedData) != 0:
        # germanStations = self.verifyData(formatedData)
        # germanStations2 = self.verifyData2(formatedData)
        germanStations = self.verifyData3(formatedData)
        # print(germanStations == germanStations2 == germanStations3)
        if len(germanStations):
          self.storeData(germanStations)
      partialCity = self.nextPartialCity(partialCity)
      requestCounter += 1
    self.close("stations", "partialCities.txt")

  @wrapper
  def run2(self):
    lastStationId = self.startup("stations", "lastStationId.txt")
    # stationsPath = os.getcwd()+os.sep+"stations"+os.sep+"stations.db"
    # con = sqlite3.connect(stationsPath)
    cur = self.dbConnect.cursor()
    request = cur.execute(f"select stationId from stations where stationId>'{lastStationId}' order by stationId asc")
    for i in range(10):
      stationId = request.fetchone()[0]
      if lastStationId > stationId:
        continue
      self.backwards(stationId, lastStationId)
      lastStationId = self.forwards(stationId)
    self.close("stations", "lastStationId.txt")
    cur.close()

  def run3(self):
    """
    post-processing: add the right country to the database
    define a box (min and max values for lat and lng)
    all the others are passed to verify and verify2 (in batches)
    """
    pass

  def backwards(self, stationId, lastStationId):
    stationId = str(int(stationId) - 1).rjust(9,"0")
    while lastStationId < stationId:
      data = self.get(stationId)
      formatedData = self.formatData(data)
      if len(formatedData) == 1:
        self.storeData(formatedData)
        print(stationId, 175)
      else:
        return
      stationId = str(int(stationId) - 1).rjust(9,"0")

  def forwards(self, stationId):
    lastStationId = stationId
    stationId = str(int(stationId) + 1).rjust(9,"0")
    #while True:
    for i in range(10):
      data = self.get(stationId)
      formatedData = self.formatData(data)
      if len(formatedData) == 1:
        self.storeData(formatedData)
        print(stationId, 189)
        lastStationId = stationId
        self.lastPartialRequests.append(lastStationId)
        stationId = str(int(stationId) + 1).rjust(9,"0")
      else:
        return lastStationId
    return lastStationId

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
    try:
      jData = json.loads(data)
    except:
      print(repr(data))
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
      if lat.startswith("-") and len(lat) < 7:
        lat = "-" + lat.lstrip("-").rjust(6, "0")
      elif len(lat) < 6:
        lat = lat.rjust(6, "0")
      lat = lat[:-6] + "." + lat[-6:]
      lng = station["xcoord"]
      if lng.startswith("-") and len(lng) < 7:
        lng = "-" + lng.lstrip("-").rjust(6, "0")
      elif len(lng) < 6:
        lng = lng.rjust(6, "0")
      lng = lng[:-6] + "." + lng[-6:]
      stationNewFormat = {"stationName": stationName,
                          "stationId"  : stationId,
                          "lat"        : lat,
                          "lng"        : lng,
                          "country"    : None
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
        station["country"] = "de"
        germanStations.append(station)
    return germanStations

  def verifyData2(self, stations):
    # check geolocation (german station?)
    # use a different service
    # https://nominatim.openstreetmap.org/search.php?q=50.209096+12.199638&format=jsonv2
    germanStations = list()
    for station in stations:
      lat = station["lat"]
      lng = station["lng"]
      url = f"https://nominatim.openstreetmap.org/search.php?q={lat}+{lng}&format=jsonv2"
      response = requests.get(url).json()
      addressName = response[0]["display_name"]
      if re.search("(Deutschland|Germany)$", addressName):
        station["country"] = "de"
        germanStations.append(station)
    return germanStations

  def verifyData3(self, stations):
    # check geolocations with local package
    germanStations = list()
    for station in stations:
      address = reverse_geocode.search([(float(station["lat"]),float(station["lng"]))])
      if address[0]["country_code"] == "DE":
        station["country"] = "de"
        germanStations.append(station)
        # print(station)
    return germanStations

  def storeData(self, stations):
    # check for duplicates and save into database
    # use sqlite as a start
    # dbLocation = os.getcwd() + os.sep + "stations" + os.sep + "stations.db"
    # con = sqlite3.connect(dbLocation)
    cur = self.dbConnect.cursor()
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
      self.dbConnect.commit()
    cur.close()
  

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
  db = DatabaseBuilder("id")

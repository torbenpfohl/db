"""
vl einmal am tag.
  getting or accessing an up-to-date list of stations

hauptaufgabe.
 die daten von der station holen
  a. aufbereiten und abspeichern (inkl. abfragezeit speichern)
  b. festlegen, wann die nächste anfrage stattfinden soll

extra. 
  stichprobenartig testen, ob die abstände zwischen den abfragen ok sind
"""

from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import re
import sqlite3
import os

class Station:
  """
  the 'name' of the station is automaticly inserted from the database of
  stations, it actually doesn't matter if the name is the stationId or
  the stationName
  storeData uses the stationId as the table-name in the database
  """
  dbPath = os.getcwd()+os.sep+"stations"+os.sep+"information.db"

  def __init__(self, name):
    self.excessStations = set()
    self.delayedCauses = set()
    self.name = name
    requestTimeDate = datetime.now()
    self.requestDate = requestTimeDate.strftime("%d.%m.%y")
    self.requestTime = requestTimeDate.strftime("%H:%M")
    self.init()

  def init(self):
    self.htmlDocument = self.getData()
    self.dataPackage = self.extractRelevantData(self.htmlDocument)
    print(self.delayedCauses)
    return self.dataPackage


  def getData(self):
    """
    also possible to get data with a get request
    what is better?
    """
    payload = {
      "input": self.name,
      "date": self.requestDate,
      "time": self.requestTime,
      "boardType": "dep",   # dep or arr
      "GUIREQProduct_0": "on",  # ICE-Züge
      "GUIREQProduct_1": "on",  # Intercity- und Eurocityzüge
      "GUIREQProduct_2": "on",  # Interregio- und Schnellzüge
      "GUIREQProduct_3": "on",  # Nahverkehr und sonstige Züge
      "GUIREQProduct_4": "on",  # S-Bahn
      "GUIREQProduct_5": "on",  # Busse
      "GUIREQProduct_6": "on",  # Schiffe
      "GUIREQProduct_7": "on",  # U-Bahnen
      "GUIREQProduct_8": "on",  # Straßenbahnen
      "GUIREQProduct_9": "on",  # Anruf-Sammeltaxi
      "start": "Suchen"
    }

    url = "https://reiseauskunft.bahn.de/bin/bhftafel.exe/dn?ld=43106&protocol=https:&rt=1&"

    response = requests.post(url, data=payload)
    return response.text
  
  def extractRelevantData(self, htmlDocument):
    # digitalData.page.pageInfo.version = "5.45.DB.R23.08.1.a (customer/hcudb/release/23.08.1.a.0) [Aug  5 2023]"
    # TODO: --> i.e. tracking changes to the layout!

    parsedHtml = BeautifulSoup(htmlDocument, "html.parser")
    # TODO: for speed look into lxml as a parser and using css-selectors

    # do we have to dates? i.e. do we have to account for the change 
    datesText = "".join([word for word in parsedHtml.find("div", id="sqResult").h2.strong.stripped_strings])
    dates = re.findall(r"\d{2}.\d{2}.\d{2}", datesText)
    if dates:
      rowDate = 2
    # wenn dates einen Wert hat (zwei-Elemente-Liste), dann muss ich 
    # 1. schauen, ob es ein aufeinanderfolgendes datum ist
    # 1.a. yes -> 2.
    # 1.b. no  -> no idea... (shouldn't really happen)
    # 2. schauen, ob ein tageswechsel statt findet, d.h. ob die zeit irgendwo von
    #    23:xx auf 00:xx umspringt.
    ## IDEE 1:
    # 1. alle zeiten werden auf dem "höchsten" datum initalisiert
    # 2. dann gehe ich von der letzten Reihe rückwärts durch die Liste und 
    #    prüfe, ob die vorherige Zeit (Uhrzeit inkl. Datum) kleiner ist, als
    #    die derzeitige.
    #    wenn ja, dann bleibt das datum so
    #    wenn nein, dann wird das datum für die vorherigen Einträge um 
    #    einen Tag reduziert und es geht weiter
    else:
      rowDate = 1

    # create a list of stations that are also present (but that I didn't ask for)
    otherStationsText = parsedHtml.find("p", "lastParagraph").find_all("a")
    otherStations = ["".join(a.stripped_strings) for a in otherStationsText]
    self.excessStations.update(otherStations)

    allRows = parsedHtml.find_all("tr", id=re.compile("^journeyRow_\d+"))

    planedTimeBefore = None
    dataPackages = list()
    for row in reversed(allRows):
      # do platform in the beginning because the row might not belong to the
      # requested station 
      platform = "".join(row.find("td", "platform").stripped_strings)
      platform = platform[1:] if platform.startswith("-") else platform
      platformNumber = re.search(r"^\d*", platform).group()
      if platformNumber:
        platform = platform.replace(platformNumber, "")
      if platform and platform in otherStations:
        continue

      dataPackage = dict()
      dataPackage["platformNumber"] = platformNumber

      planedTime = str(row.find("td", "time").string)
      if rowDate == 2:
        planedTime = datetime.strptime(planedTime+" "+dates[-1], "%H:%M %d.%m.%y")
        if planedTimeBefore:
          diff = planedTimeBefore - planedTime
          if diff.total_seconds() < 0:
            planedTime -= timedelta(days=1)
      else:
        planedTime = datetime.strptime(planedTime+" "+self.requestDate, "%H:%M %d.%m.%y")
      planedTimeBefore = planedTime
      dataPackage["planedTime"] = planedTime

      transportationTypePicUrl = row.find("td", "train").a.img["src"]
      transportationType = re.search("(?<=/)[a-z_]+(?=_\d+x\d+.[a-z]+$)", transportationTypePicUrl).group()
      dataPackage["transportationType"] = transportationType

      trainNameField = row.find_all("td", "train")[-1]
      trainUrl = "https://reiseauskunft.bahn.de" + str(trainNameField.a["href"])
      dataPackage["trainUrl"] = trainUrl
      # TODO: how long is the url valid?

      trainName = [re.compile(r"\s+").sub(" ", word) for word in trainNameField.stripped_strings]
      trainName = " ".join(trainName)
      dataPackage["trainName"] = trainName

      route = row.find("td", "route")
      endstation = str("".join([word for word in route.span.a.stripped_strings]))
      dataPackage["endstation"] = endstation

      print(trainName, endstation)

      # sometimes there is extra info (mostly in red) under the route-element-box
      extraInfo = route.find("div")
      if extraInfo is not None:
        extraInfos = list()
        while route.find("div"):
          extraInfo = route.div.extract()
          extraInfos.append(extraInfo)
      # TODO: what do I do with this information?
          
      partialRouteRaw = " - ".join([allStops.replace("\n", " ") for allStops in route.stripped_strings][1:])
      partialRouteRaw = [stop.lstrip("- ") for stop in re.split(r"(?<=\d{2}:\d{2})", partialRouteRaw) if len(stop) != 0]
      partialRouteRaw = [stop.split("  ") for stop in partialRouteRaw]
      partialRoute = list()
      currentStationDatetime = planedTime
      # TODO: problem with the red ancouncement text 
      #  sieht so aus als wäres es normalerweise ein div-element nach den den routen-halten
      # print(partialRouteRaw)
      for stop, time in partialRouteRaw:
        hours, minutes = time.split(":")
        planedTimeAtStationX = currentStationDatetime.replace(hour=int(hours), minute=int(minutes))
        if currentStationDatetime > planedTimeAtStationX:
          planedTimeAtStationX += timedelta(day=1)
        currentStationDatetime = planedTimeAtStationX
        partialRoute.append([stop, planedTimeAtStationX])
        stop = stop.removesuffix(" (Halt entfällt)")
        self.excessStations.update(stop)
      dataPackage["partialRoute"] = partialRoute


      # TODO: combine delayed stuff into 'issues and add a field for 'Fahrt fällt aus' with boolean datatype
      # delayedBy, delayedTime, delayedCause, canceled
      dataPackage["issues"] = dict()
      issues = row.find("td", "ris")
      issuesText = "".join([word for word in issues.stripped_strings])
      delayedTime = None
      delayedBy = None
      cause = None
      # canceled = None
      if len(issuesText) != 0:
        # TODO: also search for a new time, like a new date (if present)
        #   as well as understanding, what other configurations are possible in this cell
        delayedTimeMatch = re.search(r"\d{2}:\d{2}", issuesText)
        if delayedTimeMatch:
          delayedTimeRaw = delayedTimeMatch.group()
          cause = issuesText.replace(delayedTimeRaw, "")
          cause = cause.strip(", ")
          # delayed by
          #   if date is not available with the issuesText, than it will be
          #   obvious while calculation the delayed by value (because it will
          #   be negative)
          hours, minutes = delayedTimeRaw.split(":")
          delayedTime = planedTime.replace(hour=int(hours), minute=int(minutes))
          delayedBy = delayedTime - planedTime
          if delayedBy.total_seconds() < 0:
            delayedTime += timedelta(days=1)
            delayedBy = delayedTime - planedTime
        else:
          cause = issuesText
        # If the whole train is canceled, I do not need to make a request to the train
        # TODO: how often does this occur? is it worth to filter for it?
        # canceledPermutations = ["Fahrt fällt aus", "Halt entfällt"]
        # search in delayedCause for "Halt entfällt" and other things
        # re.search(r"", delayedCause)
        if cause != "":
          self.delayedCauses.update([cause])
      dataPackage["issues"]["delayedTime"] = delayedTime
      dataPackage["issues"]["delayedBy"] = delayedBy
      dataPackage["issues"]["cause"] = cause
      # dataPackage["issues"]["canceled"] = canceled

      # delayOnTime_dbClass = "delayOnTime" in issues.span["class"] if issues.span else None
      # dataPackage["delayOnTime"] = delayOnTime_dbClass

      dataPackages.append(dataPackage)
    return [i for i in reversed(dataPackages)]
      

class Train:
  def __init__(self, url):
    self.url = url  # TODO: enthält datum und zeit und andere parameter: welche brauche ich und ergibt es sinn, diese zu verändern? (z.B. zeit anpassen)
    self.init()
  
  def init(self):
    data = self.get(self.url)
    dataPackage = self.extractRelevantData(data)
    return dataPackage

  def get(self, url):
    response = requests.get(url)
    return response.text

  def extractRelevantData(self, data):
    parsedHtml = BeautifulSoup(data, "html.parser")

    dataPackage = dict()
    dataPackage["route"] = dict()

    *companyRaw, = parsedHtml.find("div", "tqRemarks").stripped_strings
    for entry in companyRaw:
      if re.match(r"^Betreiber:", entry):
        company = entry.removeprefix("Betreiber:").strip()
        break
      else:
        company = None
    dataPackage["company"] = company

    trainNameRaw = parsedHtml.find("div", class_="tqResults").find_next("h1").string
    trainName = " ".join(trainNameRaw.split()[2:])
    dataPackage["trainName"] = trainName

    trainDateRaw = str(parsedHtml.find("h3", class_="trainroute"))
    trainDate = re.search(r"\d{1,2}.\d{1,2}.\d{1,2}", trainDateRaw).group()
    trainDate = datetime.strptime(trainDate, "%d.%m.%y")
    dataPackage["trainDate"] = trainDate

    routeRows = parsedHtml.find_all("div", class_=re.compile(r"tqRow trainrow_\d"))
    planedCurrentDate = trainDate
    delayedCurrentDate = trainDate
    for index, row in enumerate(routeRows):
      dataPackage["route"][index] = dict()

      station = row.find("div", class_=re.compile("station")).find("a").string
      dataPackage["route"][index]["station"] = station

      # planed and delayed arrival time
      arr = row.find("div", class_="arrival")

      arrTimeRaw = [s for s in arr.stripped_strings if re.search(r"\d{1,2}:\d{2}", s)]
      arrTime = arrTimeRaw[0].split(" ")[-1] if len(arrTimeRaw) > 0 else None
      if arrTime:
        hours, minutes = arrTime.split(":")
        arrTime = planedCurrentDate.replace(hour=int(hours), minute=int(minutes))
        if arrTime < planedCurrentDate:
          # new day
          arrTime += timedelta(days=1)
        planedCurrentDate = arrTime
      dataPackage["route"][index]["planedArrTime"] = arrTime

      delayedArrTime = arrTimeRaw[-1] if len(arrTimeRaw) > 1 else None
      if delayedArrTime:
        hours, minutes = delayedArrTime.split(":")
        delayedArrTime = planedCurrentDate.replace(hour=int(hours), minute=int(minutes))
        if delayedArrTime < delayedCurrentDate:
          delayedArrTime += timedelta(days=1)
        delayedCurrentDate = delayedArrTime
      else:
        delayedCurrentDate = arrTime if arrTime is not None else delayedCurrentDate
      dataPackage["route"][index]["delayedArrTime"] = delayedArrTime

      # planed and delayed departure time
      dep = row.find("div", class_="departure")
      
      depTimeRaw = [s for s in dep.stripped_strings if re.search(r"\d{1,2}:\d{2}", s)]
      depTime = depTimeRaw[0].split(" ")[-1] if len(depTimeRaw) > 0 else None
      if depTime:
        hours, minutes = depTime.split(":")
        depTime = planedCurrentDate.replace(hour=int(hours), minute=int(minutes))
        if depTime < planedCurrentDate:
          depTime += timedelta(days=1)
        planedCurrentDate = depTime
      dataPackage["route"][index]["planedDepTime"] = depTime

      delayedDepTime = depTimeRaw[-1] if len(depTimeRaw) > 1 else None
      if delayedDepTime:
        hours, minutes = delayedDepTime.split(":")
        delayedDepTime = delayedCurrentDate.replace(hour=int(hours), minute=int(minutes))
        if delayedDepTime < delayedCurrentDate:
          delayedDepTime += timedelta(days=1)
        delayedCurrentDate = delayedDepTime
      else:
        delayedCurrentDate = depTime if depTime is not None else depTime
      dataPackage["route"][index]["delayedDepTime"] = delayedDepTime

      platformRaw = row.find("div", class_="platform")
      platform = [s for s in platformRaw.stripped_strings if re.search(r"\d+", s)]
      dataPackage["route"][index]["platform"] = platform[0] if len(platform) > 0 else None

      issuesRaw = row.find("div", class_="ris")
      *issues, = issuesRaw.stripped_strings
      dataPackage["route"][index]["issues"] = dict()
      dataPackage["route"][index]["issues"]["canceled"] = "Halt entfällt" in issues
      issues = [s for s in issues if s not in ["Aktuelles", "Halt entfällt"]]
      dataPackage["route"][index]["issues"]["cause"] = issues[0] if len(issues) > 0 else None

    return dataPackage


    # TODO: use excessStations here as well 



if __name__ == "__main__":
  print("everything's fine")
  station0 = "Reinheim(Odenw)"
  station1 = "darmstadt+ost"
  station2 = "Frankfurt(Main)Hbf"
  station3 = "darmstadt+hbf"
  station4 = "Berlin+Hbf"
  station5 = "Hamburg+Hbf"
  station6 = "Lüneburg"
  station7 = "000100001"
  station8 = "8006006"
  station9 = "ZOB, Lüneburg"
  station10 = "8098105"
  darmstadt2 = Station(station10)
  trainUrl = "https://reiseauskunft.bahn.de/bin/traininfo.exe/dn/535500/1225387/739576/191291/81?ld=4346&protocol=https:&rt=1&date=31.12.23&time=12:40&station_evaId=616917&station_type=dep&"
  # darmstadt = Train(trainUrl)
  import pprint
  pp = pprint.PrettyPrinter(indent=2)
  # pp.pprint(darmstadt2)
  # print(darmstadt2)
  

  
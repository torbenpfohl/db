"""
management 

-track version-/layout-changes

Struktur:
-> aufruf mit stations (eine oder mehrere) | später auch mit geo-information
--> die bahnhöfe werden zu bestimmten (festgelegten) zeiten abgefragt
-> für die züge, die mit stationen gefunden werden, wird ein event gescheduled

Stopp:
-> manuell beenden 
-> nach bestimmter zeit / zu bestimmter uhrzeit

TODO: Wie wird mit sich ändernden An-/Abfahrtszeiten verfahren?

"""

from api import Station, Train
import schedule
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_EXECUTED
import time
from datetime import datetime, timedelta
import redis
import sqlite3
# import asyncio
# import threading

def wrapper(func):
  def inner(*args, **kwargs):
    pass
  return inner



class Management:
  def __init__(self):
    self.run()

  def callStaticStations(self):
    """
    registers the specified stations once and schedules recurring calls to them
    """
    stations = ["Isernhagen"]
    for index, station in enumerate(stations):
      delaySeconds = 5*60 + index*30
      schedule.every(delaySeconds).seconds.do(self.callStation, station=station)

  def callStation(self, station):
    """
    calls the station and registers the jobs to get the train data
  
    gets called on a schedule 
    """
    data = Station(station).init()
    for train in data:
      trainName = train["trainName"]
      trainEndstation = train["endstation"]
      trainEndstationPlanedTime = train["partialRoute"][-1][-1]
      id = trainName + trainEndstation + str(trainEndstationPlanedTime)
      id = id.replace(" ", "")
      # annahme: eine zugnummer taucht nur einmal am tag auf
      # zusatz: add the planedTime of arrival at the endstation

      if id not in list(map(lambda x: x.id, self.scheduler.get_jobs())):
        self.scheduler.add_job(self.processTrain, args=[train], id=id)
    now = datetime.now()
    print(f"{station} was called at {now}")

  def processTrain(self, train):
    """
    I use a scheduler

    a job has a handle (id)

    lifecycle:
    1. get train data
    2. create id
    3. write data to the redis-db with the id as key
     a. if the id is a redis-key: get the data and compare to the current data
        update if necessary: update 
    4. schedule with next time
     a. if any time is older than 30? minutes: write from redis -> permanent ()
     b. schedule to next time (in the train-data)
    """

    trainData = Train(train["trainUrl"]).init()
    date = trainData["trainDate"]

    # create unique id - second try : this id is the same as the one in callStation
    name = trainData["trainName"]
    trainRoute = list(trainData["route"].values())
    lastStation = trainRoute[-1]["station"]
    lastStationPlanedTime = trainRoute[-1]["planedArrTime"]
    id = name + lastStation + str(lastStationPlanedTime)
    id = id.replace(" ", "")

    # store the current active trains in a redis-db
    # if the trains become inactive they're being stored in the actual permanant db 
    ids = self.redis.keys()
    if id in ids:
      oldTrainData = self.redis.json().get(id)  # TODO: only get values that could change
      # TODO: check for changes
      self.redis.json().set(id, ".", "test")# trainData)  # TODO: check out redis-om for saving datetime objects natively
    else:
      self.redis.json().set(id, ".", "test")# trainData)

    # when should the next request be made?
    # first mode: next time (next stop)
    currentTime = datetime.now()
    allTimes = list()
    nextRequestTime = None
    for stops in trainData["route"].values():
      a = stops["delayedArrTime"]
      b = stops["delayedDepTime"]
      c = stops["planedArrTime"]
      d = stops["planedDepTime"]
      allTimes.extend([a,b,c,d])
    for time in sorted(filter(lambda x: isinstance(x, datetime), allTimes)):
      if time > currentTime:   # maybe add a few minutes to currentTime
        nextRequestTime = time
        scheduledJobs = self.scheduler.get_jobs()
        if id in [job.id for job in scheduledJobs]:
          print(name, nextRequestTime, "!modified!")
          self.scheduler.reschedule_job(job_id=id, trigger="date", run_date=nextRequestTime)
        else:
          print(name, nextRequestTime, "!scheduled!")
          self.scheduler.add_job(self.processTrain, args=[train], id=id, name=f"{name} on the {date} to {lastStation}", trigger="date", run_date=nextRequestTime)
        break
    else:
      if currentTime - timedelta(minutes=30) > time:
        # self.sqlCursor.execute("")  #TODO: add to permanent database
        self.scheduler.remove_job(id)
        self.redis.delete(id)
      else:
        self.scheduler.reschedule_job(job_id=id, trigger="date", run_date=currentTime+timedelta(minute=15))


  def eventCall(self, event):
    print(datetime.now())
    print(event)
    print("-------------")
    print("jobs scheduled: ", self.scheduler.get_jobs())

  def run(self, mode="static"):
    self.sqlConnection = sqlite3.connect("connections.sql")
    self.sqlCursor = self.sqlConnection.cursor()
    self.redis = redis.Redis(host="localhost", port=6379, db=2, decode_responses=True)
    self.scheduler = BackgroundScheduler(job_defaults={"max_instances": 2})
    ## TODO: make the database for the scheduled task persistent, because I need to implement a traffic limit and dont want to lose tasks (but need to implement 
    #        a way to resume gracefully; i.e. some task won't be useful anymore, so I need to account and show, that details might have been lost)
    self.scheduler.start()
    self.scheduler.add_listener(self.eventCall, EVENT_JOB_EXECUTED)

    if mode == "static":
      self.callStaticStations()
    # TODO: add different modes, i.e. geo-infos
    else:
      print("wrong or no mode given")
      
    # TODO: Can I use a context manager here?  Too initalize the databases and
    #       the connections and all that?
    try:
      while True:
        schedule.run_pending()
        time.sleep(1)
    except KeyboardInterrupt:
      self.scheduler.shutdown()
      self.sqlCursor.close()
      self.sqlConnection.close()
      self.redis.flushdb()
    else:
      pass  # Close the databases and all that.

    

  
if __name__ == "__main__":
  Management()
def track_bhftafel_version(version):
  """Track version changes of bhftafel.
  
  Call from api.Station with extracted version.

  On version change: 
    Save the raw html data. 
    OR Only get the train-urls from Station and save the raw-html from Train.
    If a review of the version-changes is completed -> extract data from the raw htmls
      and go back to normal.
  """
  pass
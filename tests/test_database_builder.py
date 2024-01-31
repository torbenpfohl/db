from src import database_builder

class Test_next_partial_city:
  def test_last_letter_overflow(self):
    last = "hr_"
    next = database_builder.DatabaseBuilder._next_partial_city(last)
    assert next == "hsa"
  
  def test_second_to_last_letter_overflow(self):
    last = "h__"
    next = database_builder.DatabaseBuilder._next_partial_city(last)
    assert next == "iaa"

  def test_first_letter_overflow(self):
    last = "___"
    next = database_builder.DatabaseBuilder._next_partial_city(last)
    assert next == "aaaa"

  def test_no_overflow(self):
    last = "hrb"
    next = database_builder.DatabaseBuilder._next_partial_city(last)
    assert next == "hrc"

from ghp.types import Date, Missing, Sha


def test_date():
    date = Date("2020-12-06T20:56:56Z")
    assert date.year == 2020
    assert date.month == 12
    assert date.day == 6



def test_sha():
    sha = Sha("2f71baf0ea419b0107397db8741043c48190687a")
    assert str(sha) == "2f71baf"
    assert sha.full == "2f71baf0ea419b0107397db8741043c48190687a"


def test_missing():
    missing = Missing()
    assert not missing
    assert missing != None

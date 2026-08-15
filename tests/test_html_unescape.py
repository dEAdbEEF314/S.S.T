from sst.track_grouper import TrackManager


def test_normalize_title_unescapes_html_entities():
    # &amp; vs &
    assert TrackManager.normalize_title("Magterra - Act III &amp; IV") == TrackManager.normalize_title("Magterra - Act III & IV")
    assert TrackManager.normalize_title("Hot &amp; Spicy") == TrackManager.normalize_title("Hot & Spicy")
    
    # &#39; / &apos; / &quot;
    assert TrackManager.normalize_title("Don&#39;t Stop") == TrackManager.normalize_title("Don't Stop")
    assert TrackManager.normalize_title("&quot;Hero&quot;") == TrackManager.normalize_title('"Hero"')


def test_normalize_title_handles_none_and_empty():
    assert TrackManager.normalize_title("") == ""
    assert TrackManager.normalize_title(None) == ""

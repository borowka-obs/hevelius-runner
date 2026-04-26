

def ra_to_sexagesimal(ra: float) -> str:
    hours = int(ra)
    minutes = int((ra - hours) * 60)
    seconds = int(((ra - hours) * 60 - minutes) * 60)
    return f"{hours:02d} {minutes:02d} {seconds:02d}"

def dec_to_sexagesimal(dec: float) -> str:
    minus = dec < 0
    dec = abs(dec)
    degrees = int(dec)
    minutes = int((dec - degrees) * 60)
    seconds = int(((dec - degrees) * 60 - minutes) * 60)
    return f"{"-" if minus else ""}{degrees:02d} {minutes:02d} {seconds:02d}"



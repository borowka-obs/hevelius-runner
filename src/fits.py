"""
Utility functions to parse FITS headers.
"""


from astropy.io import fits


def get_int_header(header, sql, header_name):
    """
    Returns specified integer field from the header
    """
    if header_name not in header or not len(str(header[header_name])):
        return ""
    return "%s=%i, " % (sql, geti(header, header_name))


def get_float_header(header, sql, header_name):
    """
    Returns specified float field from the header
    """
    if header_name not in header or not len(str(header[header_name])):
        return ""
    return "%s=%f, " % (sql, getf(header, header_name))


def get_string_header(header, sql, header_name):
    """
    Returns specified string field from the header
    """
    if header_name not in header or not len(str(header[header_name])):
        return ""
    return "%s='%s', " % (sql, gets(header, header_name))

def parse_solved(h):
    """
    Returns string formatting that specifies if the frame was solved or not.
    """

    # Here's example FITS header this code is supposed to parse.
    # PA      =   6.40789182622E+001 / [deg, 0-360 CCW] Position angle of plate
    # CTYPE1  = 'RA---TAN'           / X-axis coordinate type
    # CRVAL1  =   2.74719564502E+002 / X-axis coordinate value
    # CRPIX1  =   2.04800000000E+003 / X-axis reference pixel
    # CDELT1  =  -1.77681403340E-004 / [deg/pixel] X-axis plate scale
    # CROTA1  =  -6.40789182622E+001 / [deg] Roll angle wrt X-axis
    # CTYPE2  = 'DEC--TAN'           / Y-axis coordinate type
    # CRVAL2  =  -1.37998534456E+001 / Y-axis coordinate value
    # CRPIX2  =   2.04800000000E+003 / Y-axis reference pixel
    # CDELT2  =  -1.77675999978E-004 / [deg/pixel] Y-Axis Plate scale
    # CROTA2  =  -6.40789182622E+001 / [deg] Roll angle wrt Y-axis
    # CD1_1   =  -7.76703599758E-005 / Change in RA---TAN along X-Axis
    # CD1_2   =  -1.59801261123E-004 / Change in RA---TAN along Y-Axis
    # CD2_1   =   1.59806120891E-004 / Change in DEC--TAN along X-Axis
    # CD2_2   =  -7.76679979895E-005 / Change in DEC--TAN along Y-Axis

    if "PLTSOLVD" not in h:
        return "he_solved=0, "

    solved = h["PLTSOLVD"]
    if not solved:
        return "he_solved=0, "

    # Ok, the header claims it's solved. Let's try to find it out
    q = "he_solved=1, "

    # Let's check if the first parameter is RA
    if not h["CTYPE1"] or h["CTYPE1"] != 'RA---TAN':
        print("Can't parse solved RA.")
        return "he_solved=2, "

    ra = float(h["CRVAL1"])

    # Now check declination
    if not h["CTYPE2"] or h["CTYPE2"] != 'DEC--TAN':
        print("Can't parse solved DEC.")
        return "he_solved=2, "

    dec = float(h["CRVAL2"])

    # Ok, now parse the x-axis reference pixel
    refx = int(h["CRPIX1"])
    refy = int(h["CRPIX2"])

    pixscalex = float(h["CDELT1"]) * 3600  # arcsec/pix in x direction
    pixscaley = float(h["CDELT2"]) * 3600  # arcsec/pix in y direction

    q += "he_solved_ra=%f, he_solved_dec=%f, he_solved_refx=%d, he_solved_refy=%d, he_pixscalex=%f, he_pixscaley=%f, " \
         % (ra, dec, refx, refy, pixscalex, pixscaley)

    # CD1_1   =  -7.76703599758E-005 / Change in RA---TAN along X-Axis
    # CD1_2   =  -1.59801261123E-004 / Change in RA---TAN along Y-Axis
    # CD2_1   =   1.59806120891E-004 / Change in DEC--TAN along X-Axis
    # CD2_2   =  -7.76679979895E-005 / Change in DEC--TAN along Y-Axis
    ra_change_x = float(h["CD1_1"])
    ra_change_y = float(h["CD1_2"])
    dec_change_x = float(h["CD2_1"])
    dec_change_y = float(h["CD2_2"])

    q += "he_solved_ra_change_x=%f, he_solved_ra_change_y=%f, he_solved_dec_change_x=%f, he_solved_dec_change_y=%f, " \
        % (ra_change_x, ra_change_y, dec_change_x, dec_change_y)

    return q


def parse_quality(header):

    q = ""
    if "FWHM" in header:
        q = f"he_fwhm={getf(header, 'FWHM')}, "

    if "HISTORY" not in header:
        return q

    for h in header["HISTORY"]:
        # There may be many HISTORY entries. We're looking for the one looking like this:
        # Matched 139 stars from the USNO UCAC4 Catalog
        if h.find("Matched ") == -1 or h.find("stars from the") == -1:
            continue

        h = h.strip()
        x = h.split(" ")
        stars = int(x[1])
        q += f"he_stars={stars}, "
        break

    return q


def gets(header, param):
    return header[param]


def getf(header, param):
    return float(header[param])


def geti(header, param):
    return int(header[param])


def read_fits(filename):
    """Reads FITS file, returns a copy of the primary HDU header.

    Prefer :func:`image_formats.read_header` for format-agnostic callers.
    """
    with fits.open(filename) as hdul:
        return hdul[0].header.copy()

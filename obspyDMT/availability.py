#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Simple functions to get the available stations in a certain time and spatial
domain.

Queries ArcLink and the IRIS webservices.

:copyright:
    Lion Krischer (krischer@geophysik.uni-muenchen.de), 2013
:license:
    GNU General Public License, Version 3
    (http://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import fnmatch
from lxml import etree
from obspy import UTCDateTime
import obspy.arclink
import obspy.iris
import warnings


def _get_arclink_availability(min_lat, max_lat, min_lng, max_lng, starttime,
        endtime):
    """
    Get a set of all available Arclink channels for the requested time and
    spatial domain.

    :param min_lat: Minimum latitude
    :param max_lat: Maximum latitude
    :param min_lng: Minimum longitude
    :param max_lng: Maximum longitude

    :returns: A dictionary, with the channel names as keys. Each value is also
        a dictionary, containing latitude and longitude.

    >>> print _get_arclink_availability(-10, 10, -10, 10, UTCDateTime() - 1E6,
    ...     UTCDateTime())
    {"NET.STA.LOC.CHAN": {"latitude": 0.0, "longitude": 0.0}, ...}
    """
    client = obspy.arclink.Client()
    # This command downloads network, station and channel information for
    # everything in the arclink network.
    everything = client.getNetworks(starttime, endtime)

    available_channels = {}
    stations_in_bounds = {}
    channels = []
    # First get all stations within bounds.
    for key, value in everything.iteritems():
        split_key = key.split(".")
        # Skip networks.
        if len(split_key) == 1:
            continue
        # Collect all channels in a list.
        elif len(split_key) == 4:
            channels.append((".".join(split_key[:2]), ".".join(split_key[2:])))
            continue
        # Only stations considered from here on. Skip restricted stations.
        if value.restricted:
            continue
        latitude = value.latitude
        longitude = value.longitude
        # Check if in bounds. If not continue.
        if not (min_lat <= latitude <= max_lat) or \
                not (min_lng <= longitude <= max_lng):
            continue
        stations_in_bounds[key] = {"latitude": latitude,
            "longitude": longitude}
    # Now loop over all channels, get the station, check if in bounds and if
    # yes take the channel.
    for network_station, loc_channel in channels:
        if network_station in stations_in_bounds.keys():
            available_channels["%s.%s" % (network_station, loc_channel)] = \
                stations_in_bounds[network_station]
    return available_channels


def _get_iris_availability(min_lat, max_lat, min_lng, max_lng, starttime,
        endtime):
    """
    Get a set of all available IRIS channels for the requested time and spatial
    domain.

    :param min_lat: Minimum latitude
    :param max_lat: Maximum latitude
    :param min_lng: Minimum longitude
    :param max_lng: Maximum longitude

    :returns: A dictionary, with the channel names as keys. Each value is also
        a dictionary, containing latitude and longitude.

    >>> print _get_iris_availability(-10, 10, -10, 10, UTCDateTime() - 1E6,
    ...     UTCDateTime())
    {"NET.STA.LOC.CHAN": {"latitude": 0.0, "longitude": 0.0}, ...}
    """
    available_channels = {}

    c = obspy.iris.Client()
    availability = c.availability(starttime=starttime, endtime=endtime,
            minlat=min_lat, maxlat=max_lat, minlon=min_lng, maxlon=max_lng,
            output="xml")

    # Read the StationXML like format.
    root = etree.fromstring(availability)
    # Get all stations.
    for station in root.findall("Station"):
        # Only latitude/longitude required for checking if station in bounds.
        latitude = float(station.find("Lat").text)
        longitude = float(station.find("Lon").text)
        network_code = station.get("net_code").strip()
        station_code = station.get("sta_code").strip()
        # Check if in bounds. If not continue.
        if not (min_lat <= latitude <= max_lat) or \
                not (min_lng <= longitude <= max_lng):
            continue
        # Check all channel if they are defined for
        for channel in station.findall("Channel"):
            channel_code = channel.get("chan_code").strip()
            location_code = channel.get("loc_code").strip()
            for time_span in channel.findall("Availability"):
                for extent in time_span.findall("Extent"):
                    channel_starttime = UTCDateTime(extent.get("start"))
                    channel_endtime = UTCDateTime(extent.get("end"))
                    if (channel_starttime <= starttime <= channel_endtime) \
                            and (channel_starttime <= endtime <=
                            channel_endtime):
                        # Replace component with wildcard.
                        available_channels["%s.%s.%s.%s" % (network_code,
                            station_code, location_code, channel_code)] = \
                            {"latitude": latitude, "longitude": longitude}
    return available_channels


def filter_channel_priority(channels, priorities=["HH[Z,N,E]", "BH[Z,N,E]",
        "MH[Z,N,E]", "EH[Z,N,E]", "LH[Z,N,E]"]):
    """
    This function takes a dictionary containing channels keys and returns a new
    one filtered with the given priorities list.

    For each station all channels matching the first pattern in the list will
    be retrieved. If one or more channels are found it stops. Otherwise it will
    attempt to retrieve channels matching the next pattern. And so on.

    :type channels: dict
    :param channels: A dictionary containing keys in the form
        "net.sta.loc.chan"
    :type priorities: list of strings
    :param priorities: The desired channels with descending priority. Channels
        will be matched by fnmatch.fnmatch() so wildcards and sequences are
        supported. The advisable form to request the three standard components
        of a channel is "HH[Z,N,E]" to avoid getting e.g.  rotational
        compononents.
    :returns: A new dictionary containing only the filtered items.
    """
    filtered_channels = {}
    all_locations = list(set([".".join(_i.split(".")[:3]) for _i in
        channels.keys()]))
    # Loop over all locations.
    for location in all_locations:
        chans = [_i.split(".")[-1] for _i in channels.keys() if
            _i.startswith(location)]
        current_channels = []
        for pattern in priorities:
            for chan in chans:
                if fnmatch.fnmatch(chan, pattern):
                    current_channels.append(chan)
            if current_channels:
                break
        for chan in current_channels:
            key = "%s.%s" % (location, chan)
            filtered_channels[key] = channels[key]
    return filtered_channels


def get_availability(min_lat, max_lat, min_lng, max_lng, starttime, endtime,
        logger=None):
    """
    Get a set of all available IRIS and ArcLink channels for the requested time
    and spatial domain.

    :param min_lat: Minimum latitude
    :param max_lat: Maximum latitude
    :param min_lng: Minimum longitude
    :param max_lng: Maximum longitude

    :returns: A dictionary, with the channel names as keys. Each value is also
        a dictionary, containing latitude and longitude.

    >>> print _get_iris_availability(-10, 10, -10, 10, UTCDateTime() - 1E6,
    ...     UTCDateTime())
    {"NET.STA.LOC.CHAN": {"latitude": 0.0, "longitude": 0.0}, ...}
    """
    availability = {}
    try:
        iris_availability = _get_iris_availability(min_lat, max_lat, min_lng,
            max_lng, starttime, endtime)
        availability.update(iris_availability)
    except Exception as e:
        msg = "Could not get availability from IRIS\n"
        msg += "\t%s: %s" % (e.__class__.__name__, e.message)
        if logger:
            logger.error(msg)
        else:
            warnings.warn(msg)
    try:
        arclink_availability = _get_arclink_availability(min_lat, max_lat,
            min_lng, max_lng, starttime, endtime)
        availability.update(arclink_availability)
    except Exception as e:
        msg = "Could not get availability from ArcLink\n"
        msg += "\t%s: %s" % (e.__class__.__name__, e.message)
        if logger:
            logger.error(msg)
        else:
            warnings.warn(msg)
    return availability
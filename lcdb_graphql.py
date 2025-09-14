import requests
from typing import Any, Dict, List

GRAPHQL_ENDPOINT = "https://graphql.lcdb.org"


CHECKSUM_QUERY = """
query ChecksumsQuery ($checksum:String!) {
  checksums(filter: {body: {contains: $checksum}}) {
    edges {
      node {
        source {
          id
        }
      }
    }
  }
}
"""

SOURCE_CHECKSUMS_QUERY = """
query SourceChecksums($sourceId: Int!, $first: Int = 500) {
  source(id: $sourceId) {
    id
    checksums(pagination: { first: $first }) {
      totalCount
      edges {
        node {
          id
          body          # checksum text
          description
          createdAt
        }
      }
    }
  }
}

"""
SOURCE_PERFORMANCE_QUERY = """
query PerformanceFromSource($sourceId: Int!) {
  source(id: $sourceId) {
    id
    archiveIdentifier
    circdate
    comments
    createdAt
    updatedAt
    enterUsername
    mediaSize
    mediaSizeUncompressed
    shndiskcount
    wavdiskcount
    textdoc
    performance {
      id
      date
      year
      city
      state
      venue
      comment
      set1
      set2
      set3
      artist {
        id
        name
      }
    }
  }
}
"""



def find_shnid_by_checksum(checksum: str) -> Dict[str, Any]:
    """
    Fetch artist performances for a given artist and year, filtered by checksum substring.
    Args:
        checksum (str): The checksum substring to search for.
    Returns:
        dict: The JSON/dict returned by the GraphQL query.
    """
    payload = {
        "query": CHECKSUM_QUERY,
        "variables": {
            "checksum": checksum,
        }
    }
    response = requests.post(GRAPHQL_ENDPOINT, json=payload)
    response.raise_for_status()
    return response.json()

def parse_shnid_by_checksum(query_result: dict) -> List[int]:
    """
    Parse SHNIDs from a GraphQL response based on checksum search.

    Args:
        result (dict): The JSON/dict returned by the GraphQL query.

    Returns:
        List[int]: List of SHNIDs found.
    """
    shnids = []
    for edge in iter_edges(query_result, ["data", "checksums"]):
        shnid = edge.get("node", {}).get("source", {}).get("id", None)
        if shnid is not None:
            shnids.append(shnid)
    return shnids

def find_performance_by_shnid(shnid: int) -> Dict[str, Any]:
    """
    Fetch performance and source details for a given SHNID.
    Args:
        shnid (int): The SHNID/source ID to query.
    Returns:
        dict: The JSON/dict returned by the GraphQL query.   
    """
    payload = {
        "query": SOURCE_PERFORMANCE_QUERY,
        "variables": {
            "sourceId": shnid,
        }
    }
    response = requests.post(GRAPHQL_ENDPOINT, json=payload)
    response.raise_for_status()
    return response.json()

def parse_performance_by_shnid(query_result: dict):
    """
    Parse performance information (with artist) from a GraphQL response.

    Args:
        result (dict): The JSON/dict returned by the GraphQL query.

    Returns:
        dict: Parsed values with keys for source and performance info.
    """
    src = query_result.get("data", {}).get("source", {}) or {}

    perf = src.get("performance", {}) or {}
    artist = perf.get("artist", {}) or {}

    parsed = {
        "source_id": src.get("id"),
        "archive_identifier": src.get("archiveIdentifier"),
        "circdate": src.get("circdate"), 
        "comments": src.get("comments"),
        "createdAt": src.get("createdAt"),
        "updatedAt": src.get("updatedAt"),
        "enterUsername": src.get("enterUsername"),
        "mediaSize": src.get("mediaSize"),
        "mediaSizeUncompressed": src.get("mediaSizeUncompressed"),
        "shndiskcount": src.get("shndiskcount"),
        "wavdiskcount": src.get("wavdiskcount"),
        "textdoc": src.get("textdoc"),
        "performance_id": perf.get("id"),
        "date": perf.get("date"),
        "year": perf.get("year"),
        "city": perf.get("city"),
        "state": perf.get("state"),
        "venue": perf.get("venue"),
        "comment": perf.get("comment"),
        "set1": perf.get("set1"),
        "set2": perf.get("set2"),
        "set3": perf.get("set3"),
        "artist_id": artist.get("id"),
        "artist_name": artist.get("name"),

    }
    return parsed



def find_checksums_by_shnid(shnid: int) -> Dict[str, Any]:
    """
    Fetch artist performances for a given artist and year, filtered by checksum substring.
    """
    payload = {
        "query": SOURCE_CHECKSUMS_QUERY,
        "variables": {
            "sourceId": shnid,
        }
    }
    response = requests.post(GRAPHQL_ENDPOINT, json=payload)
    response.raise_for_status()
    return response.json()

def parse_checksums_by_shnid(query_result: dict, shnid: int, checksums: dict):
  for edge in iter_edges(query_result,["data","source","checksums"]):
      node = edge.get("node", {})
      checksum_id = node.get("id", None)
      description = node.get("description", None)
      createdAt = node.get("createdAt", None)
      body = node.get("body", None)
      if checksum_id and body:
          if shnid in checksums:
              checksums[shnid][checksum_id] = [description, body, createdAt]
          else:
              checksums[shnid] = {checksum_id: [description, body, createdAt]}
  

# ARTIST_PERFORMANCES_QUERY = """
# query ArtistPerformancesByYearAndChecksum(
#   $artistName: String!
#   $year:       Int!
#   $checksum:   String!
# ) {
#   artistsRoot(filter: { name: { eq: $artistName } }) {
#     edges {
#       node {
#         id
#         name
#         performances(filter: { year: { eq: $year } }) {
#           edges {
#             node {
#               date
#               venue
#               city
#               state
#               sources {
#                 edges {
#                   node {
#                     archiveIdentifier
#                     checksums(filter: { body: { contains: $checksum } }) {
#                       edges {
#                         node {
#                           body
#                           createdAt
#                         }
#                       }
#                     }
#                   }
#                 }
#               }
#             }
#           }
#         }
#       }
#     }
#   }
# }
# """


# SOURCE_QUERY = """
# query (
#   $id: Int!
#   $filter: Filter_Source_Checksums
#   $pagination: Pagination
#   $filter2: Filter_Source_Identifier
#   $pagination2: Pagination
#   $filter3: Filter_Source_UserPerformances
#   $pagination3: Pagination
#   $filter4: Filter_User
#   $pagination4: Pagination
# ) {
#   source(id: $id) {
#     archiveIdentifier
#     checksums(filter: $filter, pagination: $pagination) {
#       totalCount    
#     }
#     circdate
#     comments
#     createdAt
#     dummyColumn
#     enterUsername
#     id
#     identifier(filter: $filter2, pagination: $pagination2) {
#       totalCount
#     }
#     mediaSize
#     mediaSizeUncompressed
#     performance {
#       changeComment
#       city
#       comment
#       createdAt
#       date
#       festival_lock
#       id
#       isCompilation
#       merge_lock
#       ref_festival
#       ref_venue
#       set1
#       set2
#       set3
#       showsuserid
#       spotlight_date
#       staffpick_date
#       state
#       title
#       updatedAt
#       venue
#       year
#     }
#     shndiskcount
#     textdoc
#     updatedAt
#     userPerformances(filter: $filter3, pagination: $pagination3) {
#       totalCount
#     }
#     users(filter: $filter4, pagination: $pagination4) {
#       totalCount
#     }
#     wavdiskcount
#   }
# }
# """              
  #return checksums
# def find_performance_by_shnid(id: int) -> Dict[str, Any]:
#     """
#     Fetch artist performances for a given artist and year, filtered by checksum substring.
#     """
#     payload = {
#         "query": SOURCE_QUERY,
#         "variables": {
#             "id": id,
#         }
#     }
#     response = requests.post(GRAPHQL_ENDPOINT, json=payload)
#     response.raise_for_status()
#     return response.json()




# def fetch_performances(artist_name: str, year: int, checksum: str) -> Dict[str, Any]:
#     """
#     Fetch artist performances for a given artist and year, filtered by checksum substring.
#     """
#     payload = {
#         "query": ARTIST_PERFORMANCES_QUERY,
#         "variables": {
#             "artistName": artist_name,
#             "year": year,
#             "checksum": checksum
#         }
#     }
#     response = requests.post(GRAPHQL_ENDPOINT, json=payload)
#     response.raise_for_status()
#     return response.json()

# def filter_performances_by_checksum(data: Dict[str, Any]) -> List[Dict[str, Any]]:
#     """
#     Return performance nodes where at least one source has a non-empty checksum list.
#     """
#     matching_performances: List[Dict[str, Any]] = []
#     artist_edges = data.get("data", {}).get("artistsRoot", {}).get("edges", [])
#     for artist_edge in artist_edges:
#         perf_edges = artist_edge.get("node", {}).get("performances", {}).get("edges", [])
#         for perf_edge in perf_edges:
#             perf_node = perf_edge.get("node", {})
#             sources = perf_node.get("sources", {}).get("edges", [])
#             for src in sources:
#                 checks = src.get("node", {}).get("checksums", {}).get("edges", [])
#                 if checks:
#                     matching_performances.append(perf_node)
#                     break
#     return matching_performances


# def get_sources_for_artist_year(artist_name: str, year: int) -> List[Dict[str, Any]]:
#     query = """
# query ArtistSourcesByYear($artistName: String!, $year: Int!) {
#       artistsRoot(filter: { name: { eq: $artistName } }) {
#         edges {
#           node {
#             performances(filter: { year: { eq: $year } }) {
#               edges {
#                 node {
#                   sources {
#                     edges {
#                       node {
#                         id
#                       }
#                     }
#                   }
#                 }
#               }
#             }
#           }
#         }
#       }
#     }
#     """
#     payload = {"query": query, "variables": {"artistName": artist_name, "year": year}}
#     resp = requests.post(GRAPHQL_ENDPOINT, json=payload)
#     resp.raise_for_status()
#     data = resp.json()

#     seen = set()
#     #sources_list: List[Dict[str, Any]] = []
#     artist_edges = data.get("data", {}).get("artistsRoot", {}).get("edges", [])
#     for artist_edge in artist_edges:
#         perf_edges = artist_edge.get("node", {}).get("performances", {}).get("edges", [])
#         for perf_edge in perf_edges:
#             src_edges = perf_edge.get("node", {}).get("sources", {}).get("edges", [])
#             for src_edge in src_edges:
#                 src = src_edge.get("node", {})
#                 key = src.get("id")
#                 print(type(key))
#                 #if key and key not in seen:
#                 #seen.add(key['id'])
#                     #sources_list.append(src)
#     return list(seen)

def iter_edges(result: dict, path: list[str]):
    """
    Safely yield edge dicts from a nested GraphQL response.

    Args:
        result: The JSON/dict returned from the GraphQL query.
        path: A list of keys to descend into before reaching "edges".

    Yields:
        Each edge dict (or {} if missing).
    """
    container = result
    for key in path:
        container = container.get(key, {})
    for edge in container.get("edges", []):
        yield edge or {}

# Example usage:
if __name__ == "__main__":

  checksum = "2340b22937822e2aeb1b4ce6a0dc12fc"
  #checksum = "3528e996afc1b9809019ba5ffd9a150c"

  shnids = []
  checksums = {}  
  performances = {}
  result = find_shnid_by_checksum(checksum)
  shnids = parse_shnid_by_checksum(result)

  
  for shnid in shnids:
    result = find_checksums_by_shnid(shnid)
    parse_checksums_by_shnid(result, shnid,checksums)

  for shnid in checksums.keys():
      result = find_performance_by_shnid(shnid)
      performances[shnid] = parse_performance_by_shnid(result)

  for shnid in performances.keys():
      performance = performances[shnid]
      for key, value in performance.items():
          print(f"{key}: {value}")


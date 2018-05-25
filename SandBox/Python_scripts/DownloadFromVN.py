"""
DownloadFromVN: retrieves main data from VisioNature website and store to json files.

Copyright (C) 2018, Daniel Thonon

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import sys
import getopt
import requests
from requests_oauthlib import OAuth1
import json
import gzip
import logging
import configparser
from pathlib import Path

logging.basicConfig(level="INFO")
logger = logging.getLogger(__name__)

def getTaxoGroups(file_store):
    """
    Read the taxo_groups files and return the list of taxo groups
    """
    # TODO: loop on all possible files
    file_json = str(Path.home()) + '/' + file_store + '/json/' + \
        'taxo_groups_1_1.json.gz'
    logger.debug('Reading taxo_groups file {}'.format(file_json))
    with gzip.open(file_json, 'rb') as g:
        taxo_groups = json.loads(g.read().decode('utf-8'))

    taxo_groups_list = list()
    for taxo in taxo_groups['data']:
        if (taxo['access_mode'] != 'none'):
            taxo_groups_list.append(taxo['id'])
    logger.info('Found {} taxo_groups in downloaded files'.format(len(taxo_groups_list)))
    logger.debug(taxo_groups_list)
    return taxo_groups_list

# def appendNoDuplicates(init_dict, duplicate):
#     """
#     Add elements from duplicate to init_dict, removing elements already in init_list
#     """
#     for sp in duplicate:
#         if (sp['is_used'] == '1') and (sp['id'] not in init_list):
#             init_list[sp['id']] =
#     return init_list

def getSpecies(file_store):
    """
    Read the species files and return the list of species
    """

    # Get list of taxo_groups to iterate over
    taxo_groups = getTaxoGroups(file_store)

    # Loop on available taxo_groups
    species_list = dict()
    for taxo in taxo_groups:
        i = 1
        while (i < 999):
            file_json = str(Path.home()) + '/' + file_store + '/json/' + \
                'species_' + taxo + '_' + str(i) + '.json.gz'
            if not Path(file_json).is_file():
                break

            logger.debug('Reading species file {}'.format(file_json))
            with gzip.open(file_json, 'rb') as g:
                species = json.loads(g.read().decode('utf-8'))

            i += 1

            for sp in species['data']:
                logger.debug('Adding species {}, from taxo_groups {} '.format(sp['id'], taxo))
                species_list[sp['id']] = taxo

    logger.info('Found {} species in downloaded files'.format(len(species_list)))

    # species_list = {508:1, 3260:3}
    logger.debug(species_list)
    return species_list

def getLocalAdminUnits(file_store):
    """
    Read the local_admin_units files and return the list of units
    """
    # TODO: loop on all possible files
    file_json = str(Path.home()) + '/' + file_store + '/json/' + \
        'local_admin_units_1_1.json.gz'
    logger.info('Reading local_admin_units file {}'.format(file_json))
    with gzip.open(file_json, 'rb') as g:
        local_admin_units = json.loads(g.read().decode('utf-8'))

    local_admin_units_list = list(map(lambda x: x['id'], local_admin_units['data']))
    logger.debug(local_admin_units_list)
    return local_admin_units_list

class DownloadTable:
    """
    Download from an API controler, named table (i.e. species).
    """

    # Constants for different lists of subqueries
    NO_LIST = 0  # No subquery, just request all data
    TAXO_GROUPS_LIST = 1  # Loop subquery on taxo_groups
    SPECIES_LIST = 2  # Loop subquery on species
    ADMIN_UNITS_LIST = 3  # Loop subquery on local_admin_units (communes)

    def __init__(self, site, user_email, user_pw, oauth, table, file_store,
                 by_list = NO_LIST, max_download=10):
      self.site = site
      self.user_email = user_email
      self.user_pw = user_pw
      self.oauth = oauth
      self.table = table
      self.file_store = file_store
      self.by_list = by_list
      self.max_download = max_download

    def get_table(self):
        """
        Get all date from one API controler.

        Loop on calling API for chunks of data and store result in compressed json files.
        """

        # Mandatory parameters.
        params = {'user_email': self.user_email, 'user_pw': self.user_pw}

        # Create range based on type of get_table
        if (self.by_list == self.NO_LIST):
            api_range = range(1, 2)
        elif (self.by_list == self.TAXO_GROUPS_LIST):
            api_range = getTaxoGroups(self.file_store)
        elif (self.by_list == self.SPECIES_LIST):
            api_range = getSpecies(self.file_store)
        elif (self.by_list ==  self.ADMIN_UNITS_LIST):
            api_range = getLocalAdminUnits(self.file_store)
        else:
            logger.error('Unknown list {}'.format(self.by_list))
            return(self.by_list)

        nb_elements = 0  # Totalizer for all elements received
        for i in api_range:
            nb_xfer = 1  # Sequence number for transfers, restarting for each group

            # Add specific parameters if needed
            if (self.by_list == self.NO_LIST):
                logger.info('Getting data from table {} direct'.format(self.table))
            elif (self.by_list == self.TAXO_GROUPS_LIST):
                logger.info('Getting data from table {}, id_taxo_group {}'.format(self.table, i))
                params['id_taxo_group'] = str(i)
                params['is_used'] = '1'
            elif (self.by_list == self.SPECIES_LIST):
                logger.info('Getting data from table {}, id_species {}, id_taxo {}'.format(self.table, i, api_range[i]))
                params['id_taxo_group'] = api_range[i]
                params['id_species'] = i
            elif (self.by_list ==  self.ADMIN_UNITS_LIST):
                logger.info('Getting data from table {}, id_commune {}'.format(self.table, i))
                params['id_commune'] = str(i)
            else:
                logger.error('Unknown list {}'.format(self.by_list))
                return(self.by_list)

            # Loop on data requests until end of transfer
            while True:

                # GET from API
                logger.debug('Params: {}'.format(params))
                resp = requests.get(url=self.site+self.table+'/', auth=self.oauth, params=params)
                logger.debug(resp.url)
                logger.debug(resp.request.headers)
                logger.debug(resp.headers)
                if resp.status_code != 200:
                    print('GET status code = {}, for table {}'.format(resp.status_code, self.table))
                    return(resp.status_code)

                # Is the content zipped or compressed?
                if ('content_encoding' in resp.headers):
                    logger.debug(resp.headers['content_encoding'])
                else:
                    logger.debug('No content_encoding')

                # Pretty print to string before store
                resp_dict = resp.json()
                resp_pretty = json.dumps(resp_dict, sort_keys=True, indent=4, separators=(',', ': '))

                # Save in json file, if not empty
                if (len(resp_dict['data']) > 0):
                    nb_elements += len(resp_dict['data'])
                    file_json = str(Path.home()) + '/' + self.file_store + '/json/' + \
                        self.table + '_' + str(i) + '_' + str(nb_xfer) + '.json'
                    file_json_gz = file_json + '.gz'
                    logger.info('Received {} elements, storing json data to {}'.format(len(resp_dict['data']), file_json_gz))
                    # with open(file_json.encode(), 'w') as outfile:
                    #     json.dump(resp_dict, outfile)
                    with gzip.open(file_json_gz, 'wb', 9) as g:
                        g.write(resp_pretty.encode())

                # Is there more data to come?
                if (('transfer-encoding' in resp.headers) and (resp.headers['transfer-encoding'] == 'chunked')):
                    logger.info('Chunked transfer => requesting for more, with key: {}'.format(resp.headers['pagination_key']))
                    # Update request parameters to get next chunk
                    params['pagination_key'] = resp.headers['pagination_key']
                    nb_xfer += 1
                else:
                    logger.info('Non-chunked transfer => finished requests')
                    if ('pagination_key' in params):
                        del params['pagination_key']
                    break

        return nb_elements


def usage():
    """
    Print usage message.
    """
    print('DownloadSpecies')


def main(argv):
    """
    Main.
    """

    # Get options
    try:
        opts, args = getopt.getopt(argv, 'h:', ['help'])
    except getopt.GetoptError:
        usage()
        return(2)

    for opt, arg in opts:
        # print(opt, arg)
        if opt in ('-h', '--help'):
            usage()
            return()
        else:
            assert False, 'Unknown option'
            return(2)

    # Read configuration parameters
    config = configparser.ConfigParser()
    config.read(str(Path.home()) + '/.evn.ini')

    # Import parameters in local variables
    evn_client_key = config['site']['evn_client_key']
    evn_client_secret = config['site']['evn_client_secret']
    evn_user_email = config['site']['evn_user_email']
    evn_user_pw = config['site']['evn_user_pw']
    evn_base_url = config['site']['evn_site']
    evn_file_store = config['site']['evn_file_store']

    protected_url = evn_base_url + 'api/'  # URL to GET species
    logger.info('Getting data from {}'.format(protected_url))

    # Using OAuth1 auth helper
    oauth = OAuth1(evn_client_key, client_secret=evn_client_secret)

    # # -------------------
    # # Organizational data
    # # -------------------
    # # Get entities in json format
    # t1 = DownloadTable(protected_url, evn_user_email, evn_user_pw, oauth, 'entities', evn_file_store, \
    #                    DownloadTable.NO_LIST, 50)
    # nb_entities = t1.get_table()
    # logger.info('Received {} entities'.format(nb_entities))
    #
    # # Get export_organizations in json format
    # t1 = DownloadTable(protected_url, evn_user_email, evn_user_pw, oauth, 'export_organizations', evn_file_store, \
    #                    DownloadTable.NO_LIST, 50)
    # nb_export_organizations = t1.get_table()
    # logger.info('Received {} export_organizations'.format(nb_export_organizations))

    # --------------
    # Taxonomic data
    # --------------
    # Get taxo_groups in json format
    t1 = DownloadTable(protected_url, evn_user_email, evn_user_pw, oauth, 'taxo_groups', evn_file_store, \
                       DownloadTable.NO_LIST, 50)
    nb_taxo_groups = t1.get_table()
    logger.info('Received {} taxo_groups'.format(nb_taxo_groups))
    # getTaxoGroups(evn_file_store)

    # Get species in json format
    t1 = DownloadTable(protected_url, evn_user_email, evn_user_pw, oauth, 'species', evn_file_store, \
                       DownloadTable.TAXO_GROUPS_LIST, 50)
    nb_species = t1.get_table()
    logger.info('Received {} species'.format(nb_species))
    # getSpecies(evn_file_store)

    # ----------------
    # Observation data
    # ----------------
    # Get observations in json format
    t1 = DownloadTable(protected_url, evn_user_email, evn_user_pw, oauth, 'observations', evn_file_store, \
                       DownloadTable.SPECIES_LIST, 50)  # test limit
    nb_species = t1.get_table()
    logger.info('Received {} observations'.format(nb_species))

    # # ------------------------
    # # Geographical information
    # # ------------------------
    # # Get territorial_units in json format
    # t1 = DownloadTable(protected_url, evn_user_email, evn_user_pw, oauth, 'territorial_units', evn_file_store, \
    #                    DownloadTable.NO_LIST, 10)
    # nb_territorial_units = t1.get_table()
    # logger.info('Received {} territorial_units'.format(nb_territorial_units))
    #
    # # Get grids in json format
    # t1 = DownloadTable(protected_url, evn_user_email, evn_user_pw, oauth, 'grids', evn_file_store, \
    #                    DownloadTable.NO_LIST, 10)
    # nb_grids = t1.get_table()
    # logger.info('Received {} grids'.format(nb_grids))
    #
    # # Get local_admin_units in json format
    # t1 = DownloadTable(protected_url, evn_user_email, evn_user_pw, oauth, 'local_admin_units', evn_file_store, \
    #                    DownloadTable.NO_LIST, 10)
    # nb_local_admin_units = t1.get_table()
    # logger.info('Received {} local_admin_units'.format(nb_local_admin_units))
    #
    # # Get places in json format
    # t1 = DownloadTable(protected_url, evn_user_email, evn_user_pw, oauth, 'places', evn_file_store, \
    #                    DownloadTable.ADMIN_UNITS_LIST, nb_local_admin_units + 50)  # Assuming 50 empty local_admin_units
    # nb_places = t1.get_table()
    # logger.info('Received {} places'.format(nb_places))

# Main wrapper
if __name__ == "__main__":
    main(sys.argv[1:])

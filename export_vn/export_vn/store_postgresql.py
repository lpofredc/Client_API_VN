"""Methods to store Biolovision data to Postgresql database.


Methods

- store_data      - Store generic data structure to file

Properties

-

"""
import sys
import logging
import json
from sqlalchemy import create_engine, update, select
from sqlalchemy import Table, Column, Integer, String, Float, DateTime
from sqlalchemy import MetaData, ForeignKey
from sqlalchemy.sql import and_, or_, not_
from pyproj import Proj, transform


# version of the program:
from setuptools_scm import get_version
__version__ = get_version(root='../..', relative_to=__file__)

class StorePostgresqlException(Exception):
    """An exception occurred while handling download or store. """

class StorePostgresql:
    """Provides store to Postgresql database method."""

    def __init__(self, config):
        self._config = config
        # Get tables definition from Postgresql DB
        db_string = 'postgresql+psycopg2://' + \
                    self._config.db_user + \
                    ':' +\
                    self._config.db_pw + \
                    '@' + \
                    self._config.db_host + \
                    ':' + \
                    self._config.db_port + \
                    '/' + \
                    self._config.db_name
        dbschema = self._config.db_schema_import
        self._metadata = MetaData(schema=dbschema)
        logging.info('Connecting to database %s', self._config.db_name)

        # Connect
        self._db = create_engine(db_string, echo=False)
        conn = self._db.connect()
        conn.execute('SET search_path TO {},public'.format(dbschema))

        # Get dbtable definition
        self._metadata.reflect(bind=self._db)
        self._table_defs = {'entities': {'type': 'simple',
                                            'metadata': None},
                            'forms': {'type': 'simple',
                                              'metadata': None},
                            'local_admin_units': {'type': 'geometry',
                                                   'metadata': None},
                            'observations': {'type': 'observation',
                                             'metadata': None},
                            'places': {'type': 'geometry',
                                       'metadata': None},
                            'species': {'type': 'simple',
                                        'metadata': None},
                            'taxo_groups': {'type': 'simple',
                                            'metadata': None},
                            'territorial_units': {'type': 'simple',
                                                  'metadata': None}}
        self._table_defs['entities']['metadata'] = self._metadata.tables[dbschema + '.entities_json']
        self._table_defs['forms']['metadata'] = self._metadata.tables[dbschema + '.forms_json']
        self._table_defs['local_admin_units']['metadata'] = self._metadata.tables[dbschema + '.local_admin_units_json']
        self._table_defs['observations']['metadata'] = self._metadata.tables[dbschema + '.observations_json']
        self._table_defs['places']['metadata'] = self._metadata.tables[dbschema + '.places_json']
        self._table_defs['species']['metadata'] = self._metadata.tables[dbschema + '.species_json']
        self._table_defs['taxo_groups']['metadata'] = self._metadata.tables[dbschema + '.taxo_groups_json']
        self._table_defs['territorial_units']['metadata'] = self._metadata.tables[dbschema + '.territorial_units_json']

        # Finished with DB
        conn.close()

    @property
    def version(self):
        """Return version."""
        return __version__

    # ----------------
    # Internal methods
    # ----------------
    def _store_simple(self, controler, items_dict):
        """Write items_dict to database.

        Converts each element to JSON and store to database in a tables
        named from controler.

        Parameters
        ----------
        controler : str
            Name of API controler.
        items_dict : dict
            Data returned from API call.

        Returns
        -------
        int
            Count of items stored (not exact for observations, due to forms).
        """

        # Loop on data array to store each element to database
        logging.info('Storing %d items from %s to database', len(items_dict['data']), controler)
        conn = self._db.connect()
        for elem in items_dict['data']:
            # Convert to json
            items_json = json.dumps(elem)
            logging.debug('Storing element %s',
                          items_json)
            stmt = select([self._table_defs[controler]['metadata'].c.id,
                           self._table_defs[controler]['metadata'].c.site]).\
                    where(and_(self._table_defs[controler]['metadata'].c.id==elem['id'], \
                               self._table_defs[controler]['metadata'].c.site==self._config.site))
            result = conn.execute(stmt)
            row = result.fetchone()
            if row == None:
                logging.debug('Element not found in database, inserting new row')
                stmt = self._table_defs[controler]['metadata'].insert().\
                        values(id=elem['id'],
                               site=self._config.site,
                               item=items_json)
            else:
                logging.debug('Element %s found in database, updating row', row[0])
                stmt = self._table_defs[controler]['metadata'].update().\
                        where(and_(self._table_defs[controler]['metadata'].c.id==elem['id'], \
                                   self._table_defs[controler]['metadata'].c.site==self._config.site)).\
                        values(id=elem['id'],
                               site=self._config.site,
                               item=items_json)
            result = conn.execute(stmt)

        # Finished with DB
        conn.close()

        return len(items_dict['data'])

    def _store_geometry(self, controler, items_dict):
        """Add Lambert 93 coordinates and pass to _store_simple.

        Add X, Y Lambert coordinates to each item and then
        send to _store_simple for database storage

        Parameters
        ----------
        controler : str
            Name of API controler.
        items_dict : dict
            Data returned from API call.

        Returns
        -------
        int
            Count of items stored (not exact for observations, due to forms).
        """

        in_proj = Proj(init='epsg:4326')
        out_proj = Proj(init='epsg:2154')
        # Loop on data array to reproject
        for elem in items_dict['data']:
            elem['coord_x_l93'], elem['coord_y_l93'] = transform(in_proj, out_proj,
                                                                 elem['coord_lon'],
                                                                 elem['coord_lat'])
        return self._store_simple(controler, items_dict)

    def _store_1_observation(self, controler, conn, elem, in_proj, out_proj):
        """Process and store a single observation.

        - find insert or update date
        - simplity data to remove redundant items: dates... (TBD)
        - add Lambert 93 coordinates
        - store json in Postgresql

        Parameters
        ----------
        controler : str
            Name of API controler.
        conn :
            sqlalchemy connection to database
        elem : dict
            Single observation to process and store.
        in_proj :
            Projection used in input item.
        out_proj :
            Projection added to item.
        """
        # Insert simple sightings, each row contains id, update timestamp and full json body
        logging.debug('Storing observation %s to database', elem)
        # Find last update timestamp
        if ('update_date' in elem['observers'][0]):
            update_date = elem['observers'][0]['update_date']['@timestamp']
        else:
            update_date = elem['observers'][0]['insert_date']['@timestamp']

        # Add Lambert 93 coordinates
        elem['observers'][0]['coord_x_l93'], elem['observers'][0]['coord_y_l93'] = \
            transform(in_proj, out_proj,
                      elem['observers'][0]['coord_lon'],
                      elem['observers'][0]['coord_lat'])
        elem['place']['coord_x_l93'], elem['place']['coord_y_l93'] = \
            transform(in_proj, out_proj,
                      elem['place']['coord_lon'],
                      elem['place']['coord_lat'])

        # Store in Postgresql
        items_json = json.dumps(elem)
        logging.debug('Storing element %s',
                      items_json)
        stmt = select([self._table_defs[controler]['metadata'].c.id,
                       self._table_defs[controler]['metadata'].c.site]).\
                where(and_(self._table_defs[controler]['metadata'].c.id==elem['observers'][0]['id_sighting'], \
                           self._table_defs[controler]['metadata'].c.site==self._config.site))
        result = conn.execute(stmt)
        row = result.fetchone()
        if row == None:
            logging.debug('Element not found in database, inserting new row')
            stmt = self._table_defs[controler]['metadata'].insert().\
                    values(id=elem['observers'][0]['id_sighting'],
                           site=self._config.site,
                           update_ts=update_date,
                           item=items_json)
        else:
            logging.debug('Element %s found in database, updating row', row[0])
            stmt = self._table_defs[controler]['metadata'].update().\
                    where(and_(self._table_defs[controler]['metadata'].c.id==elem['observers'][0]['id_sighting'], \
                               self._table_defs[controler]['metadata'].c.site==self._config.site)).\
                    values(id=elem['observers'][0]['id_sighting'],
                           site=self._config.site,
                           update_ts=update_date,
                           item=items_json)
        result = conn.execute(stmt)

    def _store_observation(self, controler, items_dict):
        """Iterate through observations or forms and store.

        Checks if sightings or forms and iterate on each sighting
        - find insert or update date
        - simplity data to remove redundant items: dates... (TBD)
        - add Lambert 93 coordinates
        - store json in Postgresql

        Parameters
        ----------
        controler : str
            Name of API controler.
        items_dict : dict
            Data returned from API call.

        Returns
        -------
        int
            Count of items stored (not exact for observations, due to forms).
        """
        # Insert simple sightings, each row contains id, update timestamp and full json body
        in_proj = Proj(init='epsg:4326')
        out_proj = Proj(init='epsg:2154')
        conn = self._db.connect()
        nb_obs = 0
        for i in range(0, len(items_dict['data']['sightings'])):
            elem = items_dict['data']['sightings'][i]
            self._store_1_observation(controler, conn, elem, in_proj, out_proj)
            nb_obs += 1

        if ('forms' in items_dict['data']):
            for f in range(0, len(items_dict['data']['forms'])):
                for i in range(0, len(items_dict['data']['forms'][f]['sightings'])):
                    elem = items_dict['data']['forms'][f]['sightings'][i]
                    self._store_1_observation(controler, conn, elem, in_proj, out_proj)
                    nb_obs += 1

        # Finished with DB
        conn.close()
        logging.debug('Stored %d observations or forms to database', nb_obs)
        return nb_obs

    # ---------------
    # External methods
    # ---------------
    def store(self, controler, seq, items_dict):
        """Write items_dict to database.

        Processing depends on controler, as items_dict structure varies.
        Converts each element to JSON and store to database in a tables
        named from controler.

        Parameters
        ----------
        controler : str
            Name of API controler.
        seq : str
            (Composed) sequence of data stream => Unused for db
        items_dict : dict
            Data returned from API call.

        Returns
        -------
        int
            Count of items stored (not exact for observations, due to forms).
        """
        if self._table_defs[controler]['type'] == 'simple':
            nb_item = self._store_simple(controler, items_dict)
        elif self._table_defs[controler]['type'] == 'geometry':
            nb_item = self._store_geometry(controler, items_dict)
        elif self._table_defs[controler]['type'] == 'observation':
            nb_item = self._store_observation(controler, items_dict)
        else:
            raise StorePostgresqlException('Not implemented')

        return nb_item

__author__ = "MarkusDoepfert"
__credits__ = ""
__license__ = ""
__maintainer__ = "MarkusDoepfert"
__email__ = "markus.doepfert@tum.de"

# Imports
import os
import pandas as pd
import polars as pl
import numpy as np
import time
import logging
import traceback
from datetime import datetime

# TODO: Considerations
# - Each timestep is a new instance of the agent
# - The commands are executed in the order of the methods


class Lem:

    def __init__(self, timetable):
        self.timetable = timetable

        # Available actions (see market config)
        self.actions = {
            'clear': self.clear,
            'settle': self.settle,
        }

        # Available clearing types (see market config)
        self.types = {
            None: {},  # no clearing (ponder if even part of it or just, if None, then just a wholesale market)
            'ex-ante': {},
            'ex-post': {},
        }

        # Available clearing methods (see market config)
        self.methods = {
            'pda': {},  # periodic double auction
            'community': {},  # community-based clearing
        }

        # Available pricing methods (see market config)
        self.pricing = {
            'uniform': {},  # uniform pricing
            'discriminatory': {},  # discriminatory pricing
        }

        # Available coupling methods (see market config)
        # Note: This probably means that the upper market draws the offers and bids from the lower market (ponder)
        self.coupling = {
            None: {},  # no coupling
            'above_c': {},  # continuously post offers and bids on market above
            'above_l': {},  # post offers and bids on market above at the last moment
            'below_c': {},  # continuously post offers and bids on market below
            'below_l': {},  # post offers and bids on market below at the last moment
        }

    def execute(self):
        """Executes all the actions of the LEM defined in the timetable"""

        # Generated with co-pilot so might be not quite right
        # Get the actions to be executed
        actions = self.timetable['actions']
        # Get the clearing type
        clearing_type = self.timetable['clearing_type']
        # Get the clearing method
        clearing_method = self.timetable['clearing_method']
        # Get the pricing method
        pricing_method = self.timetable['pricing_method']
        # Get the coupling method
        coupling_method = self.timetable['coupling_method']

        # Execute the actions
        for action in actions:
            self.actions[action](clearing_type, clearing_method, pricing_method, coupling_method)

        # Couple market
        # Note: This is not part of the actions, but is executed after the actions
        self.couple_markets(clearing_type, clearing_method, pricing_method, coupling_method)

        # Determine balancing energy
        self.determine_balancing_energy()

        # Post results to database
        self.post_results()

    def clear(self, clearing_type, clearing_method, pricing_method, coupling_method, **kwargs):
        """Clears the market

        Note that if the markets are coupled there might already be postings that need to be included (but then again they should be posted by the previous market so might be irrelevant)
        """
        ...

    def settle(self, **kwargs):
        """Settles the market"""
        ...

    def couple_markets(self, clearing_type, clearing_method, pricing_method, coupling_method, **kwargs):
        """Couple the market"""

        # Executed with the unsettled bids and offers, if any exist and coupling method to be done
        ...

    def determine_balancing_energy(self, **kwargs):
        """Determines the balancing energy"""
        ...

    def post_results(self, **kwargs):
        """Posts the results to the database"""
        ...

    def _ex_ante(self):
        """Clears the market ex-ante"""
        ...

    def _ex_post(self):
        """Clears the market ex-post"""
        ...

    def _pda(self):
        """Clears the market with the periodic double auction method"""
        ...

    def _community(self):
        """Clears the market with the community-based clearing method"""
        ...

    def _uniform(self):
        """Prices the market with the uniform pricing method"""
        ...

    def _discriminatory(self):
        """Prices the market with the discriminatory pricing method"""
        ...

    def _above(self):
        """Coupling with the market above"""
        ...

    def _above_c(self):
        """Coupling with the market above"""
        ...

    def _above_l(self):
        """Coupling with the market above"""
        ...

    def _below(self):
        """Coupling with the market below"""
        ...

    def _below_c(self):
        """Coupling with the market below"""
        ...

    def _below_l(self):
        """Coupling with the market below"""
        ...
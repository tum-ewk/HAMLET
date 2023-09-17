# Similar to optimization that it contains the class and calls the classes with functions
import polars as pl
import pytz
from datetime import datetime, timedelta
import inspect
import ast
from hamlet import constants as c
import hamlet.executor.utilities.forecasts.models as models
import hamlet.functions as f


class Forecaster:
    """
    A class to make forecast for the given agent.

    This class contains all the functions related to forecasting. The forecasting models are defined in a separate file
    model.py and will be collected in this class. Each agent class initializes a forecaster for itself and calls the
    forecast models through this class. There's no direct connection between forecast models and agent class.

    Attributes:
        config_dict: dictionary contains forecast config
        forecasts: forecast results
        train_data: data to feed into models
        all_models: all available forecast models
        used_models: chosen models for forecasting
        weather: weather dataframe
        length_to_predict: length to predict everytime when calling forecast
        start_ts: timestamp when simulation starts

    Methods:

    """

    def __init__(self, agentDB, marketsDB: dict, general: dict):
        self.agentDB = agentDB  # AgentDB object
        self.marketsDB = marketsDB  # MarketDB object
        self.general = general  # general data

        # empty variables, to be initialized
        self.config_dict = {}   # dictionary contains forecast config
        self.train_data = {}    # data to feed into models
        self.all_models = {}    # all available forecast models
        self.used_models = {}   # chosen models for forecasting
        self.weather = pl.LazyFrame()   # weather dataframe
        self.length_to_predict = 0  # length to predict everytime when calling forecast
        self.start_ts = datetime.now()   # timestamp when simulation starts
        self.refit_period = 0   # period, after which models should be refitted

    ########################################## PUBLIC METHODS ##########################################

    def init_forecaster(self):
        """Initialize forecaster with corresponding model for each plant, initial fitting of models."""
        # initialize config dict
        self.__assign_config_dict()

        # initialize general data
        self.__init_general_data()

        # generate full train data
        self.__prepare_train_data()

        # initialize forecast models
        self.__assign_models()

    def update_forecaster(self, id, dataframe, target=True):
        """Update training data for e.g. local market. Will replace the given dataframe to the corresponding part of
        train data. """
        # TODO: implement this function
        # new train data with new target
        self.train_data[id]['target'] = dataframe

        # update model
        self.used_models[id].update_train_data(self.train_data[id])

    def make_all_forecasts(self, timetable):
        """Make forecasts for all plants."""
        forecasts = {}   # dict to store all forecast results
        current_ts = timetable.select(c.TC_TIMESTAMP).collect().item(0, 0)      # get current timestep from timetable

        # make forecast for each plant and assign results to a dict
        for id in self.config_dict.keys():
            forecast = self.__make_forecast_for_id(current_ts, id)
            forecasts[id] = forecast

        # summarize all forecasts to a dataframe (lazyframe)
        forecasts = self.__summarize_forecasts_to_df(forecasts, current_ts)

        # Return the forecasts dataframe (lazyframe)
        return forecasts

    ########################################## PRIVATE METHODS ##########################################

    """relevant for initialization"""

    def __init_general_data(self):
        """Initialize general variables and dataframes."""
        # assign weather data
        self.weather = self.general['weather']

        # get start time
        self.start_ts = self.general['general']['time']['start']

        # get length to predict
        self.length_to_predict = self.agentDB.account['ems']['fcasts']['horizon']

        # get refit period
        self.refit_period = self.agentDB.account['ems']['fcasts']['retraining']

    def __assign_config_dict(self):
        """Summarize all forecast config into one dictionary."""
        # assign market config
        market_config = self.agentDB.account['ems']['market']['fcast']  # get forecast config for market
        for market_name in self.marketsDB.keys():   # assign market config dict for each market
            wholesale_id = market_name + '_wholesale'
            local_id = market_name + '_local'

            # add to config dict
            # TODO: the param here is hard-coded!
            self.config_dict[wholesale_id] = {'method': market_config['wholesale'],
                                              'naive': {'offset': 1},
                                              'perfect': {}}
            self.config_dict[local_id] = {'method': market_config['local'],
                                          'naive': {'offset': 1},
                                          'perfect': {}}

        # assign plants config
        for plant_id in self.agentDB.plants.keys():
            if 'fcast' in self.agentDB.plants[plant_id].keys():     # only take plants which need to be forecasted
                self.config_dict[plant_id] = self.agentDB.plants[plant_id]['fcast']
                self.config_dict[plant_id]['type'] = self.agentDB.plants[plant_id]['type']
                chosen_model = self.config_dict[plant_id]['method']
                # if no additional parameters given for the chosen model, assign an empty dict
                if chosen_model not in list(self.config_dict[plant_id].keys()):
                    self.config_dict[plant_id][chosen_model] = {}

    def __assign_models(self):
        """
        Assign related forecast models.

        Get all models from models module and assign them to a dict according to the given keywords, then assign the
        chosen forecast model for each plant / market. Initialization and initial fitting of the chosen forecast models.
        """
        # get all models from imported module
        all_models = inspect.getmembers(models, inspect.isclass)
        for model in all_models:
            if hasattr(model[1], 'name'):  # include only models defined in the imported module with right format
                self.all_models[model[1].name] = model[1]

        # assign and initialize the chosen models
        for id in self.config_dict.keys():
            chosen_model = self.config_dict[id]['method']  # keyword of the chosen model as string
            # check if there's extra keyword arguments for model initialization
            self.used_models[id] = self.all_models[chosen_model](self.train_data[id],
                                                                 **self.config_dict[id][chosen_model])

            # initial fitting
            # self.used_models[id].fit(current_ts=self.start_ts, length_to_predict=self.length_to_predict,
            #                          **self.config_dict[id][chosen_model])

    def __prepare_train_data(self):
        """
        Prepare train data according to the given features.

        The training data is a dictionary with two keys: features and target. The value of each key is a polars
        lazyframe.
        """
        self.__prepare_markets_target_data()

        self.__prepare_plants_target_data()

        self.__prepare_ev_target_data()

        self.__prepare_features()

    def __prepare_markets_target_data(self):
        """Prepare target data for markets."""
        for market_name, marketDB in self.marketsDB.items():  # assign market config dict for each market
            # TODO: retailers columns need to be updated in constants, here change hard-coded column names
            target_wholesale = marketDB.retailer    # get retailer data

            # pre-processing for retailer data
            # calculate market data resolution
            target = f.calculate_timedelta(target_df=target_wholesale, reference_ts=self.start_ts)
            target = target.filter(pl.col('timedelta') != 0)  # delete the row for the current ts
            target = target.with_columns(abs(pl.col('timedelta')))  # set timedelta to absolute value
            # the smallest timedelta is the resolution
            resolution = target.select(pl.min('timedelta')).collect().item().seconds

            # add a day before simulation with the same data
            # TODO: here one day is hard-coded!
            day_before = f.slice_dataframe_between_times(target_df=target_wholesale, reference_ts=self.start_ts,
                                                         duration=1, unit='day')
            day_before = day_before.with_columns((pl.col(c.TC_TIMESTAMP) - pl.duration(days=1, seconds=resolution))
                                                 .alias(c.TC_TIMESTAMP))
            target_wholesale = pl.concat([day_before, target_wholesale], how='vertical')

            # initial prepare for the wholesale market
            self.train_data[market_name + '_wholesale'] = {'target': target_wholesale}

            # initial prepare for the local market
            # TODO: check which columns should be taken for local market
            target_local = target_wholesale.select(c.TC_TIMESTAMP, 'energy_price_sell')\
                                           .rename({'energy_price_sell': 'energy_price_sell_local'})
            self.train_data[market_name + '_local'] = {'target': target_local}

    def __prepare_plants_target_data(self):
        """Prepare target data for plants."""
        # get plants' timeseries
        plants_timeseries = self.agentDB.timeseries

        # get all related plants except timestamps
        plants_id = plants_timeseries.columns
        plants_id.remove(c.TC_TIMESTAMP)

        # get target data
        for column in plants_id:
            plant_id = column.split('_')[0]
            # assign target data to dict
            self.train_data[plant_id] = {'target': plants_timeseries.select(c.TC_TIMESTAMP, column)}

    def __prepare_ev_target_data(self):
        """Prepare target data for EVs."""
        plants_timeseries = self.agentDB.timeseries     # get plants' timeseries
        # get plants id for EV
        for plant_id in self.config_dict.keys():
            if 'type' in self.config_dict[plant_id].keys() and self.config_dict[plant_id]['type'] == c.P_EV:
                ev_id = plant_id
                target = plants_timeseries.select(c.TC_TIMESTAMP, ev_id + '_availability', ev_id + '_energy_consumed')
                self.train_data[ev_id] = {'target': target}

    def __prepare_features(self):
        """If there's features assigned to the plant with given id, add them to the corresponding train data."""
        for id in self.train_data.keys():
            # if given, get features
            chosen_model = self.config_dict[id]['method']  # keyword of the chosen model as string

            # check if features columns need to be added
            if ('features' in self.config_dict[id][chosen_model].keys() and
                    ast.literal_eval(self.config_dict[id][chosen_model]['features'])):
                # get features name as strings
                features_name = ast.literal_eval(self.config_dict[id][chosen_model]['features'])

                # get features data from weather file
                features = self.weather

                # add time features
                if 'time' in features_name:
                    features_name.remove('time')
                    features = features.with_columns(pl.col(c.TC_TIMESTAMP).dt.hour().alias('hour'))
                    features = features.with_columns(pl.col(c.TC_TIMESTAMP).dt.month().alias('month'))
                    features_name += ['hour', 'month']

                # add other weather features
                features_name += [c.TC_TIMESTAMP, c.TC_TIMESTEP]
                features = features.select(features_name)
            else:
                features = pl.LazyFrame()

            self.train_data[id]['features'] = features

    """relevant for data processing"""

    def __make_forecast_for_id(self, current_ts, id):
        """Make forecast for the plant with given id. Re-fit model before forecasting if needed."""
        chosen_model = self.config_dict[id]['method']  # keyword of the chosen model as string

        # refit model if needed
        offset = (current_ts - self.start_ts.replace(tzinfo=pytz.UTC)).seconds  # offset between current ts and start ts
        # check offset % refit period to see if the current time is exactly the beginning of a new refitting period
        if offset % self.refit_period == 0:
            self.used_models[id].fit(current_ts=current_ts, length_to_predict=self.length_to_predict,
                                     **self.config_dict[id][chosen_model])

        return self.used_models[id].predict(current_ts=current_ts, length_to_predict=self.length_to_predict,
                                            **self.config_dict[id][chosen_model])  # predict

    def __summarize_forecasts_to_df(self, forecasts: dict, current_ts):
        """
        Summarize all forecasts from dictionary to one polars lazyframe.

        All forecasts should have the same length and stored as a lazyframe.
        """
        # generate a column contains time index
        timestamp = f.slice_dataframe_between_times(target_df=self.agentDB.timeseries, reference_ts=current_ts,
                                                    duration=self.length_to_predict).select(c.TC_TIMESTAMP)

        forecasts_list = [timestamp.collect()]     # list which will contain all forecast lazyframes

        for id, forecast in forecasts.items():
            # remove time column(s) for all forecasts
            if c.TC_TIMESTAMP in forecast.columns:
                forecast = forecast.drop(c.TC_TIMESTAMP)
            if c.TC_TIMESTEP in forecast.columns:
                forecast = forecast.drop(c.TC_TIMESTEP)

            # add lazyframe to list
            # TODO: are there smarter solutions?
            forecasts_list.append(forecast.collect())

        # summarize everything together
        forecasts_df = pl.concat(forecasts_list, how='horizontal')

        return forecasts_df
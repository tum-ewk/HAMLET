__author__ = "MarkusDoepfert"
__credits__ = ""
__license__ = ""
__maintainer__ = "MarkusDoepfert"
__email__ = "markus.doepfert@tum.de"

import hamlet.constants as c
from pprint import pprint
import numpy as np


class LinopyComps:

    def __init__(self, name, timeseries, **kwargs):

        # Get the data
        self.name = name
        self.ts = timeseries
        self.info = kwargs

    def define_variables(self, model, **kwargs):
        raise NotImplementedError()

    @staticmethod
    def define_constraints(model):
        return model

    def define_electricity_variable(self, model, comp_type, lower, upper):
        # Define the power variable
        model.add_variables(name=f'{self.name}_{comp_type}_{c.ET_ELECTRICITY}', lower=lower, upper=upper, integer=True)

        return model

    def define_heat_variable(self, model, comp_type, lower, upper):
        # Define the power variable
        model.add_variables(name=f'{self.name}_{comp_type}_{c.ET_HEAT}', lower=lower, upper=upper, integer=True)

        return model


class Market(LinopyComps):

    def __init__(self, name, **kwargs):

        # Call the parent class constructor
        super().__init__(name, **kwargs)

        # Get specific object attributes
        self.power = 0  # TODO: This needs to be changed to the market result (0 is as if no energy was purchased)

    def define_variables(self, model, **kwargs):
        energy_type = kwargs['energy_type']

        # Define the market variable
        model.add_variables(name=f'{self.name}_{energy_type}', lower=self.power, upper=self.power, integer=True)

        return model


class Balancing(LinopyComps):

    def __init__(self, name, **kwargs):

        # Call the parent class constructor
        super().__init__(name, **kwargs)

        # Get specific object attributes
        self.power = 10000000000  # TODO: This needs to be changed to the max available balancing energy

    def define_variables(self, model, **kwargs):
        energy_type = kwargs['energy_type']

        # Define the balancing variable
        x = model.add_variables(name=f'{self.name}_{energy_type}', lower=-self.power, upper=self.power, integer=True)

        return model


class InflexibleLoad(LinopyComps):

    def __init__(self, name, **kwargs):

        # Call the parent class constructor
        super().__init__(name, **kwargs)

        # Get specific object attributes
        self.power = self.ts[f'{self.name}_power'][0]

    def define_variables(self, model, **kwargs):
        comp_type = kwargs['comp_type']

        # Define the power variable
        model = self.define_electricity_variable(model, comp_type=comp_type, lower=self.power, upper=self.power)

        return model


class FlexibleLoad(LinopyComps):

    def __init__(self, name, **kwargs):

        # Call the parent class constructor
        super().__init__(name, **kwargs)

        # Get specific object attributes
        print(self.ts)


class Heat(LinopyComps):

    def __init__(self, name, **kwargs):

        # Call the parent class constructor
        super().__init__(name, **kwargs)

        # Get specific object attributes
        self.heat = self.ts[f'{self.name}_heat'][0]

    def define_variables(self, model, **kwargs):
        comp_type = kwargs['comp_type']

        # Define the power variable
        model = self.define_heat_variable(model, comp_type=comp_type, lower=self.heat, upper=self.heat)

        return model


class Dhw(LinopyComps):

    def __init__(self, name, **kwargs):

        # Call the parent class constructor
        super().__init__(name, **kwargs)

        # Get specific object attributes
        self.heat = self.ts[f'{self.name}_dhw'][0]

    def define_variables(self, model, **kwargs):
        comp_type = kwargs['comp_type']

        # Define the power variable
        model = self.define_heat_variable(model, comp_type=comp_type, lower=self.heat, upper=self.heat)

        return model


class SimplePlant(LinopyComps):

    def __init__(self, name, **kwargs):

        # Call the parent class constructor
        super().__init__(name, **kwargs)

        # Get specific object attributes
        self.power = self.ts[f'{self.name}_power'][0]
        self.controllable = self.info['sizing']['controllable']
        self.lower = 0 if self.controllable else self.power

    def define_variables(self, model, **kwargs):
        comp_type = kwargs['comp_type']

        # Define the power variable
        model = self.define_electricity_variable(model, comp_type=comp_type, lower=self.lower, upper=self.power)

        return model


class Pv(SimplePlant):

    def __init__(self, name, **kwargs):

        # Call the parent class constructor
        super().__init__(name, **kwargs)


class Wind(SimplePlant):

    def __init__(self, name, **kwargs):

        # Call the parent class constructor
        super().__init__(name, **kwargs)


class FixedGen(SimplePlant):

    def __init__(self, name, **kwargs):

        # Call the parent class constructor
        super().__init__(name, **kwargs)


class Hp(LinopyComps):

    def __init__(self, name, **kwargs):

        # Call the parent class constructor
        super().__init__(name, **kwargs)

        # Get specific object attributes
        print(self.ts)
        self.cop = self.ts[f'{self.name}_cop'][0]


class Ev(LinopyComps):

    def __init__(self, name, **kwargs):

        # Call the parent class constructor
        super().__init__(name, **kwargs)

        # Get specific object attributes
        self.comp_type = None
        self.target = kwargs['targets'][f'{self.name}'][0] # TODO: This needs to be changed as it will be this only in the first instance but then name_ev_target after the first time
        self.availability = self.ts[f'{self.name}_availability'][0]
        self.energy = self.ts[f'{self.name}_energy_consumed'][0]
        # For now this is always charging at home. In the future this can depend on the availability column if it shows
        # the location instead of availability at home. Most of it is already prepared.
        self.capacity = self.info['sizing']['capacity']
        self.charging_power_home = self.info['sizing']['charging_home']
        self.charging_power_AC = self.info['sizing']['charging_AC']
        self.charging_power_DC = self.info['sizing']['charging_DC']
        self.charging_power = self.charging_power_home  # To be changed once more sophisticated EV modelling available
        self.efficiency = self.info['sizing']['charging_efficiency']
        self.v2g = self.info['sizing']['v2g']

        # Charging scheme
        self.scheme = self.info['charging_scheme']

        # Kwargs variables
        self.dt = kwargs['delta'].total_seconds()  # time delta in seconds
        self.soc = kwargs['socs'][f'{self.name}'][0] - self.energy  # state of charge at timestep (energy)


        self.energy_to_full = self.capacity - self.soc  # energy needed to charge to full

        # Define the charging power variables (depends on availability and v2g)
        if self.availability:
            # Set upper bound by calculating max charging power according to capacity, soc, efficiency and dt
            self.upper = int(round(min(self.charging_power,
                                       self.energy_to_full / self.efficiency / (self.dt * c.SECONDS_TO_HOURS))))

            # Set lower bound based on v2g
            if self.v2g:
                # Set lower bound by calculating max discharging power according to capacity, soc, efficiency and dt
                self.lower = -int(round(min(self.charging_power,
                                            self.soc * self.efficiency / (self.dt * c.SECONDS_TO_HOURS))))
            else:
                self.lower = 0

        else:
            self.lower, self.upper = 0, 0

    def define_variables(self, model, **kwargs):
        self.comp_type = kwargs['comp_type']

        # Define the power variable
        model = self.define_electricity_variable(model, comp_type=self.comp_type, lower=self.lower, upper=self.upper)

        # Define the target variable
        model.add_variables(name=f'{self.name}_{self.comp_type}_target',
                            lower=self.target, upper=self.target, integer=True)

        # Define the deviation variable for positive and negative deviations
        # Deviation when more is charged than according to target
        model.add_variables(name=f'{self.name}_{self.comp_type}_deviation_pos',
                            lower=0, upper=self.upper - self.target, integer=True)
        # Deviation when less is discharged than according to target
        model.add_variables(name=f'{self.name}_{self.comp_type}_deviation_neg',
                            lower=0, upper=self.target - self.lower, integer=True)

        return model

    def define_constraints(self, model):

        # Define the deviation constraint
        equation_pos = (model.variables[f'{self.name}_{self.comp_type}_power']
                        - model.variables[f'{self.name}_{self.comp_type}_target']
                        <= model.variables[f'{self.name}_{self.comp_type}_deviation_pos'])

        equation_neg = (model.variables[f'{self.name}_{self.comp_type}_power']
                        - model.variables[f'{self.name}_{self.comp_type}_target']
                        >= model.variables[f'{self.name}_{self.comp_type}_deviation_neg'])

        model.add_constraints(equation_pos, name=f'{self.name}_deviation_pos')
        model.add_constraints(equation_neg, name=f'{self.name}_deviation_neg')

        return model


class SimpleBattery(LinopyComps):

    def __init__(self, name, **kwargs):

        # Call the parent class constructor
        super().__init__(name, **kwargs)

        # Get specific object attributes
        self.comp_type = None
        self.target = kwargs['targets'][f'{self.name}'][0]
        self.capacity = self.info['sizing']['capacity']
        self.charging_power = self.info['sizing']['power']
        self.efficiency = self.info['sizing']['efficiency']
        self.b2g = self.info['sizing']['b2g']
        self.g2b = self.info['sizing']['g2b']

        # Kwargs variables
        self.dt = kwargs['delta'].total_seconds()  # time delta in seconds
        self.soc = kwargs['socs'][f'{self.name}'][0]  # state of charge at timestep (energy)
        self.energy_to_full = self.capacity - self.soc  # energy needed to charge to full


        # Define the charging and discharging power variables (depend on capacity, soc, efficiency and dt)
        self.upper = int(round(min(self.charging_power,
                         self.energy_to_full / self.efficiency / (self.dt * c.SECONDS_TO_HOURS))))
        self.lower = -int(round(min(self.charging_power,
                          self.soc * self.efficiency / (self.dt * c.SECONDS_TO_HOURS))))

    def define_variables(self, model, **kwargs):
        self.comp_type = kwargs['comp_type']

        # Define the power variable
        model = self.define_electricity_variable(model, comp_type=self.comp_type, lower=self.lower, upper=self.upper)

        # Define the target variable
        model.add_variables(name=f'{self.name}_{self.comp_type}_target',
                            lower=self.target, upper=self.target, integer=True)

        # Define the deviation variable for positive and negative deviations
        # Deviation when more is charged than according to target
        model.add_variables(name=f'{self.name}_{self.comp_type}_deviation_pos',
                            lower=0, upper=self.upper - self.target, integer=True)
        # Deviation when less is discharged than according to target
        model.add_variables(name=f'{self.name}_{self.comp_type}_deviation_neg',
                            lower=0, upper=self.target - self.lower, integer=True)

        return model

    def define_constraints(self, model):

        # Define the deviation constraint
        equation_pos = (model.variables[f'{self.name}_{self.comp_type}_power']
                        - model.variables[f'{self.name}_{self.comp_type}_target']
                        <= model.variables[f'{self.name}_{self.comp_type}_deviation_pos'])

        equation_neg = (model.variables[f'{self.name}_{self.comp_type}_power']
                        - model.variables[f'{self.name}_{self.comp_type}_target']
                        >= model.variables[f'{self.name}_{self.comp_type}_deviation_neg'])

        model.add_constraints(equation_pos, name=f'{self.name}_deviation_pos')
        model.add_constraints(equation_neg, name=f'{self.name}_deviation_neg')

        return model


class Battery(SimpleBattery):

    def __init__(self, name, **kwargs):

        # Call the parent class constructor
        super().__init__(name, **kwargs)


class Psh(SimpleBattery):

    def __init__(self, name, **kwargs):

        # Call the parent class constructor
        super().__init__(name, **kwargs)


class Hydrogen(SimpleBattery):

    def __init__(self, name, **kwargs):

        # Call the parent class constructor
        super().__init__(name, **kwargs)


class HeatStorage(LinopyComps):

    def __init__(self, name, **kwargs):

        # Call the parent class constructor
        super().__init__(name, **kwargs)

        # Get specific object attributes
        print(self.ts)
        print(self.info)

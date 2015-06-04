import urllib
import json
import time
from aws_parser import demand_jsonptojson, spot_jsonptojson
from flask import Flask, render_template
app = Flask(__name__)

class Region:
    def __init__(self, region):
        self.region = region
        self.mean_price = None
        self.instances = []

    def __repr__(self):
        return 'Region(region={}, instances={})'.format(self.region, self.instances)

    def calculate_mean_price(self):
        total_price = 0.0
        for instance in self.instances:
            total_price = total_price + float(instance.price_per_vcpu)

        self.mean_price = total_price / len(self.instances)

    def calculate_instance_price_spreads(self):
        spot_instances = [i for i in self.instances if i.spot == True]
        demand_instances = [i for i in self.instances if i.demand == True]
        spreads = {}
        for spot_instance in spot_instances:
            spot_price = float(spot_instance.price_per_vcpu)
            spot_name = spot_instance.name
            for demand_instance in demand_instances:
                if demand_instance.name == spot_name:
                    demand_price = float(demand_instance.price_per_vcpu)
                    if demand_price < spot_price:
                        print(spot_instance)
                        print(demand_instance)
                    else:
                        spread = demand_price - spot_price
                        spreads[spot_name] = spread
                    break
                else:
                    continue

        return spreads


class Instance:
    def __init__(self, region, generation, name, os, vcpu, price, price_per_vcpu, spot, demand):
        self.region = region
        self.generation = generation
        self.name = name
        self.os = os
        self.vcpu = vcpu
        self.price = price
        self.price_per_vcpu = price_per_vcpu
        self.spot = spot
        self.demand = demand
    def __repr__(self):
        return 'Instance(region={}, generation={}, name={}, os={}, vcpu={}, price={}, price_per_vcpu={}, spot={}, demand={})'.format(self.region, self.generation, self.name, self.os, self.vcpu, self.price, self.price_per_vcpu, self.spot, self.demand)

class EC2Assets:
    """Main container class for all the EC2 assests we're examining."""
    def __init__(self):
        self.vcpu_dict = {}
        self.instances = []
        self.regions = []

    def get_region(self, region):
        """Get a region object from the list by name, or add it."""
        region_obj = None
        for reg in self.regions:
            if reg.region == region:
                region_obj = reg
                break    
        if region_obj:
            return region_obj
        else:
            region_obj = Region(region=region)
            self.regions.append(region_obj)
            return region_obj 

    def add_demand_instances(self, url):
        """Parse the demand instances JSON and load it into the list of objects"""
        try:
            response = urllib.request.urlopen(url);
        except:
            print("Couldn't get [{}]".format(url))
            return

        demand_json = str(response.read())
        demand_json = demand_jsonptojson(demand_json)
        data = json.loads(demand_json)
        for region in data['config']['regions']:
            region_obj = self.get_region(region['region'])
            for inst_type in region['instanceTypes']: 
                generation = inst_type['type']
                for system in inst_type['sizes']:
                    name=system['size']
                    vcpu=system['vCPU']
                    self.vcpu_dict[name]=vcpu
                    for value in system['valueColumns']:
                        if value['name']=='mswin':
                            continue

                        price = value['prices']['USD']
                        price_per_vcpu = float(price) / float(vcpu)
                        inst = Instance(region=region['region'], generation=generation, name=name, os=value['name'], vcpu=vcpu, price=price, price_per_vcpu=price_per_vcpu, spot=False, demand=True)
                        region_obj.instances.append(inst)
                        self.instances.append(inst)


    def add_spot_instances(self, url):
        """Parse the spot instances JSON and load it into the list of objects"""
        try:
            response = urllib.request.urlopen(url);
        except:
            print("Couldn't get [{}]".format(url))
            return

        spot_json = str(response.read())
        spot_json = spot_jsonptojson(spot_json)
        data = json.loads(spot_json)
        for region in data['config']['regions']:
            region_obj = self.get_region(region['region'])
            for inst_type in region['instanceTypes']: 
                generation = inst_type['type']
                for system in inst_type['sizes']:
                    name=system['size']
                    vcpu = self.vcpu_dict[name]
                    for value in system['valueColumns']:
                        price = value['prices']['USD']
                        if value['name']=='mswin' or price == "N/A*":
                            continue

                        price_per_vcpu = float(price) / float(vcpu)
                        inst = Instance(region=region['region'], generation=generation, name=name, os=value['name'], vcpu=vcpu, price=price, price_per_vcpu=price_per_vcpu, spot=True, demand=False)
                        region_obj.instances.append(inst)
                        self.instances.append(inst)


    def legacy_dict_fill(self, url):
        """Legacy systems vCPU numbers are not in the spot list, so using the demand list to fill a dict for use by spot loader"""
        try:
            response = urllib.request.urlopen(url);
        except:
            print("Couldn't get [{}]".format(url))
            return

        leagacy_json = str(response.read())
        leagacy_json = demand_jsonptojson(leagacy_json)
        data = json.loads(leagacy_json)
        for region in data['config']['regions']:
            for inst_type in region['instanceTypes']: 
                for system in inst_type['sizes']:
                    name=system['size']
                    vcpu=system['vCPU']
                    self.vcpu_dict[name]=vcpu

    def update_regions_price(self):
        for region in self.regions:
            region.calculate_mean_price()

    def find_cheapest_region(self):
        cheap_region = sorted(self.regions, key=lambda region: region.mean_price)
        return cheap_region[0:1]

    def find_cheapest(self, limit):
        cheaps = sorted(self.instances, key=lambda instance: instance.price_per_vcpu)
        return cheaps[0:limit-1]

    def find_most_expensive(self, limit):
        cheaps = sorted(self.instances, key=lambda instance: instance.price_per_vcpu, reverse=True)
        return cheaps[0:limit-1]
            


def load_data(aws, again=False):
    if again:
        del aws
        aws = EC2Assets()
    aws.legacy_dict_fill(url='http://a0.awsstatic.com/pricing/1/ec2/previous-generation/linux-od.min.js')
    aws.add_demand_instances(url='http://a0.awsstatic.com/pricing/1/ec2/linux-od.min.js')
    aws.add_spot_instances(url='http://spot-price.s3.amazonaws.com/spot.js')
    aws.update_regions_price()

@app.route('/reload')   #Thinking this could be a celery task, but for the sake of time...
def reload_data():
    load_data(aws, again=True)
    return 'Reloaded'

@app.route('/price_spread')
def price_spread():
    spread_json = '{ "regions": ['
    for index, region in enumerate(aws.regions):
        spreads = region.calculate_instance_price_spreads()
        if spreads == {}:
            spread_json = '{}, {{ "region":"{}", "instance_spreads": null }}'.format(spread_json, region.region)
            continue
        if index == 0:
            spread_json = '{} {{ "region":"{}", "instance_spreads": {} }}'.format(spread_json, region.region, json.dumps(spreads))
        else:
            spread_json = '{}, {{ "region":"{}", "instance_spreads": {} }}'.format(spread_json, region.region, json.dumps(spreads))
    spread_json = '{}] }}'.format(spread_json)
    return spread_json

@app.route('/cheapest')
def bottom_ten():
    ten_cheap = aws.find_cheapest(10)
    cheap_json = '{{ "cheapest": {} }}'.format(json.dumps(ten_cheap, default=lambda o: o.__dict__))
    return cheap_json

@app.route('/most_expensive')
def top_ten():
    ten_expensive = aws.find_most_expensive(10)
    expensive_json = '{{ "most_expensive": {} }}'.format(json.dumps(ten_expensive, default=lambda o: o.__dict__))
    return expensive_json

@app.route('/cheapest_region')
def cheapest_region():
    cheap_region = aws.find_cheapest_region()
    cheapest_region_json = '{{ "cheapest_region": {} }}'.format(json.dumps(cheap_region, default=lambda o: o.__dict__))
    return cheapest_region_json

@app.route('/')
def index_page():
    return render_template('index.html') 

if __name__ == '__main__':
    aws = EC2Assets()
    load_data(aws)
    app.run(host='0.0.0.0', port=8080, debug=True)

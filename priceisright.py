import urllib
import json
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
        print(self.mean_price)

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
    def __init__(self):
        self.vcpu_dict = {}
        self.instances = []
        self.regions = []

    def get_region(self, region):
        region_obj = None
        for reg in self.regions:
            if reg.region == region:
                region_obj = reg
                break    
        if region_obj:
            return region_obj
        else:
            r = Region(region=region)
            self.regions.append(r)
            return r 

    def add_demand_instances(self, url):
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
            
def load_data(aws):
    aws.legacy_dict_fill(url='http://a0.awsstatic.com/pricing/1/ec2/previous-generation/linux-od.min.js')
    aws.add_demand_instances(url='http://a0.awsstatic.com/pricing/1/ec2/linux-od.min.js')
    aws.add_spot_instances(url='http://spot-price.s3.amazonaws.com/spot.js')
    aws.update_regions_price()

@app.route('/price_spread')
def price_spread():
    return 'Price Spread'

@app.route('/cheapest')
def bottom_ten():
    ten_cheap = aws.find_cheapest(10)
    cheap_json = "{{ \"cheapest\": {} }}".format(json.dumps(ten_cheap, default=lambda o: o.__dict__))
    return cheap_json

@app.route('/most_expensive')
def top_ten():
    ten_expensive = aws.find_most_expensive(10)
    expensive_json = "{{ \"most_expensive\": {} }}".format(json.dumps(ten_expensive, default=lambda o: o.__dict__))
    return expensive_json

@app.route('/cheapest_region')
def cheapest_region():
    cheap_region = aws.find_cheapest_region()
    cheapest_region_json = "{{ \"cheapest_region\": {} }}".format(json.dumps(cheap_region, default=lambda o: o.__dict__))
    return cheapest_region_json

@app.route('/')
def index_page():
    return render_template('index.html') 

if __name__ == '__main__':
    aws = EC2Assets()
    load_data(aws)
    app.run(host='0.0.0.0', port=8080, debug=True)

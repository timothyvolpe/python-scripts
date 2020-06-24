import requests
import time
import csv
from lxml import html
from decimal import *

PB_PEAK_FORMAT = "https://www.peakbagger.com/peak.aspx?pid={0}"
REQUEST_COOLDOWN = 1.5 # time to wait before consecutive PB requests

us_state_abbrev = {
	'Alabama': 'AL', 'Alaska': 'AK', 'American Samoa': 'AS', 'Arizona': 'AZ',
	'Arkansas': 'AR', 'California': 'CA', 'Colorado': 'CO',
	'Connecticut': 'CT', 'Delaware': 'DE', 'District of Columbia': 'DC',
	'Florida': 'FL', 'Georgia': 'GA', 'Guam': 'GU', 'Hawaii': 'HI',
	'Idaho': 'ID', 'Illinois': 'IL', 'Indiana': 'IN', 'Iowa': 'IA',
	'Kansas': 'KS', 'Kentucky': 'KY', 'Louisiana': 'LA', 'Maine': 'ME',
	'Maryland': 'MD', 'Massachusetts': 'MA', 'Michigan': 'MI',
	'Minnesota': 'MN', 'Mississippi': 'MS', 'Missouri': 'MO', 'Montana': 'MT',
	'Nebraska': 'NE', 'Nevada': 'NV', 'New Hampshire': 'NH',
	'New Jersey': 'NJ', 'New Mexico': 'NM', 'New York': 'NY',
	'North Carolina': 'NC', 'North Dakota': 'ND',
	'Northern Mariana Islands':'MP', 'Ohio': 'OH', 'Oklahoma': 'OK',
	'Oregon': 'OR', 'Pennsylvania': 'PA', 'Puerto Rico': 'PR', 
	'Rhode Island': 'RI', 'South Carolina': 'SC', 'South Dakota': 'SD',
	'Tennessee': 'TN', 'Texas': 'TX', 'Utah': 'UT', 'Vermont': 'VT',
	'Virgin Islands': 'VI', 'Virginia': 'VA', 'Washington': 'WA',
	'West Virginia': 'WV', 'Wisconsin': 'WI', 'Wyoming': 'WY'
}

class Peak:
	def __init__(self, name, elevation, prominance, rank, pid):
		self.peak_name = name
		self.elevation = elevation
		self.prominance = prominance
		self.rank = rank
		self.pid = pid
		
		self.lat = 0
		self.long = 0
		
		self.alt_names = ""
		self.state = ""
		self.state_abbrev = ""
		
def coordinate_str_to_decimal(coord_str):
	coord_str = coord_str.replace("&deg", '')
	tokens = coord_str.split()
	lat_deg = int(tokens[0])
	lat_min = int(tokens[1].replace('\'', ''))
	lat_sec = int(tokens[2].replace("\'\'", ''))
	lat_card = tokens[3]
	lat_decimal = lat_deg + lat_min/60 + lat_sec/3600
	print("{0}/{1} = {2}".format(lat_sec, 3600, lat_sec/3600))
	
	long_deg = int(tokens[4])
	long_min = int(tokens[5].replace('\'', ''))
	long_sec = int(tokens[6].replace("\'\'", ''))
	long_card = tokens[7]
	long_decimal = long_deg + long_min/60 + long_sec/3600
	
	print("{0}, {1}".format(lat_decimal, long_decimal))

def main():
	print("Peak Info Scraper v1.0")
	print("By Timothy Volpe")
	print("\nFor use with www.peakbagger.com")
	
	ignored_unranked = True
	
	while True:
		link = input("\nEnter Link to Peak List: ")
		if not link:
			return
			
		print("Retrieving list page...")
		try:
			list_page = requests.get(link)
		except requests.exceptions.MissingSchema as err:
			print(err)
			continue
		except requests.exceptions.ConnectionError as err:
			print("Failed to connect to {0}".format(link))
			continue
		except Exception as err:
			print(err)
			return
		except:
			print("Unknown exception")
			return
		print("Success!")
		break
		
	ranked = input("Ignore Unranked (blank for yes)?:")
	if ranked:
		ignore_unranked = False
		
	list_page_tree = html.fromstring(list_page.content)
	
	titles = list_page_tree.xpath("//h1/text()")
	if titles:
		print("Found List: {0}".format(titles[0]))
	else:
		print("Unable to find list title")
		
	peaks = []
		
	peak_table = list_page_tree.xpath("//table[@class=\"gray\"]")
	if peak_table:
		print("\n\tPeak Name\t\t\tElevation\tProminance")
		print("-----------------------------------------------------------------------")
		try:
			peak_list = peak_table[0].xpath(".//tr")
			for peak_row in peak_list[2:]:
				peak_columns = peak_row.xpath(".//td")
				ranked_str = peak_columns[0].text
				if not ranked_str.strip() and ignored_unranked:
					continue
				rank = int(ranked_str.replace('.',''))
				title = peak_columns[1].xpath("./a/text()")[0]
				link = peak_columns[1].xpath("./a/@href")[0]
				pid = int(link.split("pid=")[1])
				elevation = int(peak_columns[2].text)
				prominance = int(peak_columns[3].text)
				peaks.append(Peak(title, elevation, prominance, rank, pid))
				if len(title) > 15:
					title_entry = title + "\t\t"
				else:
					title_entry = title + "\t\t\t"
				print(" {0}.\t{1}({2} ft,\t{3} ft)".format(rank, title_entry, elevation, prominance))
		except ValueError as err:
			print("Unexpected value in webpage: {0}".format(err))
		except IndexError:
			print("Missing expected element")
	else:
		print("Unable to find table body")
		return
	
	# Make sure the user wants to proceed
	check_peaks = input("Continue scraping each peak's data page (Y/n)?: ")
	if check_peaks != "Y":
		return
	# Check the page
	for peak in peaks:
		# Download the page and generate tree
		print("Retrieving info for \"{0}\"".format(peak.peak_name))
		peak_link = PB_PEAK_FORMAT.format(peak.pid)
		try:
			peak_page = requests.get(peak_link)
		except requests.exceptions.ConnectionError as err:
			print("Failed to connect to {0}".format(peak_link))
			continue
		peak_page_tree = html.fromstring(peak_page.content)
		
		try:
			first_table = peak_page_tree.xpath("//table[@class=\"gray\"]")[0]
			data_rows = first_table.xpath(".//tr")
			for drow in data_rows:
				table_data = drow.xpath(".//td")
				if table_data and (table_data[0].text is not None):
					if "Latitude" in table_data[0].text and "Longitude" in table_data[0].text:
						fullcoord = table_data[1].text_content()
						fullcoord = fullcoord.split("(Dec Deg)")[0]
						if "E" in fullcoord:
							fullcoord = fullcoord.split("E")[1]
						else:
							fullcoord = fullcoord.split("W")[1]
						coord_tokens = fullcoord.strip().split(", ")
						peak.lat = float(coord_tokens[0])
						peak.long = float(coord_tokens[1])
					if "Alternate Name(s)" in table_data[0].text:
						peak.alt_names = table_data[1].text
					if "State" in table_data[0].text:
						raw_state = table_data[1].text
						raw_state = raw_state.replace("(Highest Point)", '')
						raw_state = raw_state.strip()
						peak.state = raw_state
						if peak.state in us_state_abbrev:
							peak.state_abbrev = us_state_abbrev[peak.state]
		except ValueError as err:
			print("Unexpected value in webpage: {0}".format(err))
		except IndexError:
			print("Missing expected element")
			
		print("Peak Info:")
		print("  Latitude/Longitude: {0}, {1}".format(peak.lat, peak.long))
		print("  {0}".format(peak.alt_names))
		print("  State: {0} ({1})".format(peak.state, peak.state_abbrev))
		
		time.sleep(REQUEST_COOLDOWN)
	
	# Write to CSV file

if __name__ == "__main__":
	main()
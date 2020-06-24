"""

	MIT License

	Copyright (c) 2020 timothyvolpe

	Permission is hereby granted, free of charge, to any person obtaining a
	copy of this software and associated documentation files (the "Software"), 
	to deal in the Software without restriction, including without limitation
	the rights to use, copy, modify, merge, publish, distribute, sublicense,
	and/or sell copies of the Software, and to permit persons to whom the
	Software is furnished to do so, subject to the following conditions:

	The above copyright notice and this permission notice shall be included in
	all copies or substantial portions of the Software.

	THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
	IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
	FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
	AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
	LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
	FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
	DEALINGS IN THE SOFTWARE.

"""

import requests
import time
import csv
from lxml import html
from decimal import *

PB_PEAK_FORMAT = "https://www.peakbagger.com/peak.aspx?pid={0}"
REQUEST_COOLDOWN = 1.5 # time to wait before consecutive PB requests

CSV_FILENAME = "peaks.csv"

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
	def __init__(self, name, elevation, prominance, range, rank, pid):
		self.peak_name = name
		self.elevation = elevation
		self.prominance = prominance
		self.range = range
		self.rank = rank
		self.pid = pid
		
		self.lat = 0
		self.long = 0
		
		self.alt_names = ""
		self.state = ""
		self.state_abbrev = ""
		
def parse_peak_list(ignored_unranked, list_page):
	list_page_tree = html.fromstring(list_page.content)
	
	titles = list_page_tree.xpath("//h1/text()")
	if titles:
		print("Found List: {0}".format(titles[0]))
	else:
		print("Unable to find list title")
		
	peaks = []
		
	peak_table = list_page_tree.xpath("//table[@class=\"gray\"]")
	if peak_table:
		print("\n\tPeak Name\t\t\tElevation\tProminance\tRange")
		print("-------------------------------------------------------------------------------------------------")
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
				range = peak_columns[4].xpath("./a/text()")[0]
				peaks.append(Peak(title, elevation, prominance, range, rank, pid))
				if len(title) > 15:
					title_entry = title + "\t\t"
				else:
					title_entry = title + "\t\t\t"
				if prominance > 999:
					range_entry = "\t" + range
				else:
					range_entry = "\t\t" + range
				print(" {0}.\t{1}({2} ft,\t{3} ft){4}".format(rank, title_entry, elevation, prominance, range_entry))
		except ValueError as err:
			print("Unexpected value in webpage: {0}".format(err))
		except IndexError:
			print("Missing expected element")
	else:
		print("Unable to find table body")
		
	return peaks
	
def scrape_peak_data(peaks):
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
		
def write_peak_data(peaks, filename):
	print("\nWriting to {0}".format(filename))
	with open(filename, 'w', newline='') as csvfile:
		fieldnames = ["Peak", "Mountain", "Elevation (ft)", "Prominance (ft)",
						"Summited", "Summit Date", "Summit Count", "State",
						"Group", "Latitude, Longitude", "Trails", "Range (Level 6)", "Notes"]
		writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

		writer.writeheader()
		
		for peak in peaks:
			lat_long = "{0}, {1}".format(peak.lat, peak.long)
			writer.writerow(
					{"Peak": peak.peak_name,
					"Mountain": peak.peak_name,
					"Elevation (ft)": peak.elevation,
					"Prominance (ft)": peak.prominance,
					"Summited": "No",
					"Summit Date": "",
					"Summit Count": "",
					"State": peak.state_abbrev,
					"Group": "",
					"Latitude, Longitude": lat_long,
					"Trails": "",
					"Range (Level 6)": peak.range,
					"Notes": peak.alt_names}
				)


def main():
	print("Peak Info Scraper v1.0")
	print("By Timothy Volpe")
	print("\nFor use with www.peakbagger.com")
	
	ignored_unranked = True
	
	# Get the link list from the user
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
		
	peaks = parse_peak_list(ignored_unranked, list_page)
	
	# Make sure the user wants to proceed
	check_peaks = input("Continue scraping each peak's data page (Y/n)?: ")
	if check_peaks != "Y":
		return
	scrape_peak_data(peaks)
	
	# Write to CSV file
	write_peak_data(peaks, CSV_FILENAME)

if __name__ == "__main__":
	main()
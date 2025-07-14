#!/usr/bin/env python3

import json
import pandas as pd
import numpy as np
import calendar
from collections import defaultdict
from colorspacious import cspace_convert
import shutil
import os
import sys

# Configuration constants
TIMEZONE = "America/New_York"
NIGHT_CUTOFF_HOUR = 5	# for calendar view, before 5am counts as late night posting for previous day
MIN_RGB = (0, 0, 0)		# Black for 0 posts
MAX_RGB = (0.22, 1, 0.08)# Brightest neon green for max posts
PERCENTILE = 95
NUMBERLESS = False		# Set to False to show post counts

def get_posts_from_directory(directory):
	timestamps = []
	posts_dir = os.path.join(directory, "app.bsky.feed.post")
	if not os.path.exists(posts_dir):
		print(f"Error: Could not find posts directory at {posts_dir}")
		sys.exit(1)

	for root, _, files in os.walk(posts_dir):
		for file in files:
			filepath = os.path.join(root, file)
			with open(filepath, "r") as f:
				data = json.load(f)
				timestamps.append(data["createdAt"])

	print(f"Loaded timestamps for {len(timestamps)} posts from {directory}")
	return timestamps

def create_color_function(values):
	count_ceiling = np.percentile(values, PERCENTILE) if values else 1
	min_lab = cspace_convert(MIN_RGB, "sRGB1", "CIELab")
	max_lab = cspace_convert(MAX_RGB, "sRGB1", "CIELab")

	def colorize_text(count):
		# Normalize count
		factor = min(count / count_ceiling, 1.0)
		# Linear interpolation in LAB
		interp_lab = min_lab + (max_lab - min_lab) * factor

		# Convert back to RGB
		interp_rgb = cspace_convert(interp_lab, "CIELab", "sRGB1")
		r, g, b = [max(0, min(int(c * 255), 255)) for c in interp_rgb]

		if NUMBERLESS:
			count_text = '  '
		else:
			count_text = ' ·' if count == 0 else f'{count:2d}'
		return f"\033[48;2;{r};{g};{b}m {count_text} \033[0m"

	print(f"{PERCENTILE}th percentile ceiling clips counts above {count_ceiling:.0f} posts to brightest color.\n")
	return colorize_text, count_ceiling

def generate_hours_heatmap(posts):
	# Extract post counts by month and hour
	post_counts = defaultdict(lambda: defaultdict(int))
	for timestamp in posts:
		dt = pd.to_datetime(timestamp)
		dt = dt.tz_convert(TIMEZONE)  # posts are in zulu time

		# Create key for year-month and count by hour
		year_month = f"{dt.year}-{dt.month:02d}"
		hour = dt.hour
		post_counts[year_month][hour] += 1

	total_posts = sum(sum(hours.values()) for hours in post_counts.values())
	all_counts = [count for hours in post_counts.values() for count in hours.values()]

	colorize_text, count_ceiling = create_color_function(all_counts)

	# Print header with hour labels
	print("    ", end="")
	for hour in range(24):
		print(f" {hour:02d} ", end="")
	print("")

	sorted_months = sorted(post_counts.keys())

	# Print heatmap with each month as a row, each hour as a column
	for year_month in sorted_months:
		year, month = map(int, year_month.split('-'))
		month_name = calendar.month_abbr[month]
		if month == 1:
			month_name = f"'{year % 100}"

		print(f"{month_name} ", end="")
		for hour in range(24):
			count = post_counts[year_month][hour]
			print(colorize_text(count), end="")
		print()

def generate_days_heatmap(posts):
	# Extract post counts by day of week and hour
	post_counts = defaultdict(lambda: defaultdict(int))
	for timestamp in posts:
		dt = pd.to_datetime(timestamp)
		dt = dt.tz_convert(TIMEZONE)

		day_of_week = dt.dayofweek
		hour = dt.hour
		post_counts[day_of_week][hour] += 1

	total_posts = sum(sum(hours.values()) for hours in post_counts.values())
	all_counts = [count for hours in post_counts.values() for count in hours.values()]

	colorize_text, count_ceiling = create_color_function(all_counts)

	# Print header with hour labels
	print("    ", end="")
	for hour in range(24):
		print(f" {hour:02d} ", end="")
	print("")

	# Print heatmap with each day as a row, each hour as a column
	for day_idx in range(7):
		day_name = calendar.day_abbr[day_idx]

		print(f"{day_name} ", end="")
		for hour in range(24):
			count = post_counts[day_idx][hour]
			print(colorize_text(count), end="")
		print()

def generate_calendar_heatmap(posts):
	# Extract post counts per day on the fly
	post_counts = defaultdict(int)
	for timestamp in posts:
		dt = pd.to_datetime(timestamp)
		dt = dt.tz_convert(TIMEZONE)
		dt = dt - pd.Timedelta(hours=NIGHT_CUTOFF_HOUR)

		date_str = dt.date().isoformat()
		post_counts[date_str] += 1

	# Convert to DataFrame for easier manipulation
	df = pd.DataFrame(post_counts.items(), columns=["date", "count"])
	df["date"] = pd.to_datetime(df["date"])
	df["year"] = df["date"].dt.year
	df["month"] = df["date"].dt.month
	df["day"] = df["date"].dt.day

	colorize_text, count_ceiling = create_color_function(list(post_counts.values()))

	terminal_width = shutil.get_terminal_size((80, 20)).columns
	weekday_header = " Mo  Tu  We  Th  Fr  Sa  Su "  # Monday start
	calendar_gap = "  "
	calendar_width = len(weekday_header) + len(calendar_gap)
	max_calendars_per_row = (terminal_width + len(calendar_gap)) // calendar_width

	# Check if we need to use gapless mode (terminal can only fit one month)
	if max_calendars_per_row <= 1:
		print("   ", weekday_header)

		# Get all dates in chronological order
		all_dates = sorted([(pd.Timestamp(date), count) for date, count in post_counts.items()])

		# Find first Monday on or before the first date
		first_date = all_dates[0][0]
		days_to_subtract = first_date.weekday()
		current_date = first_date - pd.Timedelta(days=days_to_subtract)

		# Create weekly rows until after the last date
		last_date = all_dates[-1][0]

		current_week = []
		while current_date <= last_date:
			# Add each day to the current week
			count = post_counts.get(str(current_date.date()), 0)
			current_week.append(colorize_text(count))

			# If we've filled a week, print it and start a new one
			if len(current_week) == 7 or current_date == last_date:
				# Check if any day in this week is the first day of a month
				week_start = current_date - pd.Timedelta(days=len(current_week) - 1)
				month_abbr = "   "
				for i in range(len(current_week)):
					check_date = week_start + pd.Timedelta(days=i)
					if check_date.day == 1:
						month_abbr = calendar.month_abbr[check_date.month]
						# Use year abbreviation for January
						if check_date.month == 1:
							month_abbr = f"'{check_date.year % 100}"
						break

				# Pad partial week if needed
				if len(current_week) < 7:
					current_week.extend(["    "] * (7 - len(current_week)))

				# Print with month abbreviation if available, otherwise with spaces
				print(month_abbr, "".join(current_week))
				current_week = []

			current_date += pd.Timedelta(days=1)
	else:
		# Use original month-by-month display with headers
		all_weeks = []
		for (year, month), month_data in sorted(df.groupby(["year", "month"])):
			# Create a blank calendar (6 weeks max, 7 days per week)
			month_calendar = [["    " for _ in range(7)] for _ in range(6)]  # Initialize with blank spaces
			first_day, num_days = calendar.monthrange(year, month)  # Monday = 0, Sunday = 6

			# Fill in all valid days of the month (with or without posts)
			month_data_dict = {day: count for day, count in zip(month_data["day"], month_data["count"])}

			for day in range(1, num_days + 1):
				week, weekday = divmod(first_day + day - 1, 7)  # Monday starts at index 0
				count = month_data_dict.get(day, 0)
				month_calendar[week][weekday] = colorize_text(count)

			# Add non-empty weeks to the collection
			for week in month_calendar:
				if any(cell != "    " for cell in week):
					all_weeks.append((year, month, "".join(week)))

		# Print the calendar
		month_blocks = []
		current_year_month = None

		for year, month, week in all_weeks:
			if (year, month) != current_year_month:
				# Start a new month
				if month_blocks and len(month_blocks) == max_calendars_per_row:
					# Print completed row of months
					for row in zip(*month_blocks):
						print(calendar_gap.join(row))
					print()
					month_blocks = []

				# Add month header
				current_year_month = (year, month)
				month_name = calendar.month_name[month]
				header = f"{month_name} {year}".center(calendar_width - len(calendar_gap))
				month_output = [header, weekday_header]
				month_blocks.append(month_output)

			# Add week to current month
			month_blocks[-1].append(week)

		# Print any remaining months
		if month_blocks:
			for row in zip(*month_blocks):
				print(calendar_gap.join(row))

def main():
	if len(sys.argv) < 2:
		print(f"Usage: python {sys.argv[0]} <directory from .car export>")
		sys.exit(1)

	directory = sys.argv[1]
	posts = get_posts_from_directory(directory)

	generate_hours_heatmap(posts)
	print()

	generate_days_heatmap(posts)
	print()

	generate_calendar_heatmap(posts)

	print("\033[0m")  # Reset terminal colors at the end

if __name__ == "__main__":
	main()

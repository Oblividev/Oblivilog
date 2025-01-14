from matplotlib.lines import lineStyles
import sanitise
import pandas as pd
import matplotlib.pyplot as plt
import re
import glob
import logging
from typing import List, Dict
import os
from bokeh.plotting import figure, save
from bokeh.resources import CDN
from bokeh.embed import file_html
from bokeh.models import (
    ColumnDataSource, HoverTool, 
    LinearColorMapper, NumeralTickFormatter
)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# User configuration
TARGET_USERS = ['']  # Targeted users show up in the console, showing their message count. this is used for debugging.
TOP_USERS_COUNT = 50  # Number of top users to visualize

def parse_chat_data(file_path: str) -> pd.DataFrame:
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            chat_data = file.readlines()
    except Exception as e:
        logging.error(f"Error reading file {file_path}: {str(e)}")
        return pd.DataFrame(columns=['timestamp', 'username', 'message'])

    pattern = re.compile(r'\[(?P<timestamp>.+?)\] (?P<username>.+?): (?P<message>.+)')
    chat_entries = []
    for line in chat_data:
        match = pattern.match(line)
        if match:
            entry = match.groupdict()
            # Filter out gift sub notifications
            if not ("gifted a Tier 1 sub to" in entry['message'] or 
                    "is gifting" in entry['message']):
                chat_entries.append(entry)
    
    return pd.DataFrame(chat_entries)

def concatenate_dfs(file_paths: List[str]) -> pd.DataFrame:
    dfs = []
    for file_path in file_paths:
        dfs.append(parse_chat_data(file_path))
    return pd.concat(dfs, ignore_index=True)

def analyze_data(chat_df: pd.DataFrame) -> pd.Series:
    return chat_df['username'].value_counts()

def visualize_top_users(top_users: pd.Series, output_path: str):
    # Create data source with formatted numbers
    source = ColumnDataSource(data={
        'users': top_users.index,
        'counts': top_users.values,
        'counts_formatted': [f"{x:,}" for x in top_users.values]
    })

    # Create the figure with fixed y_range
    max_count = max(top_users.values)
    p = figure(
        x_range=top_users.index.tolist(),
        y_range=(0, max_count * 1.1),
        height=600,
        width=1200,
        title=f'Top Users by Message Count (Total Messages: {top_users.sum():,})',
        tools='xpan,xwheel_zoom,reset,save',
        active_scroll='xwheel_zoom',
        background_fill_color=None,
        border_fill_color=None,
        toolbar_sticky=False
    )

    # Add hover tooltips
    p.add_tools(HoverTool(tooltips=[('User', '@users'), ('Messages', '@counts_formatted')]))

    # Create and style the bar chart
    p.vbar(
        x='users', top='counts', width=0.8, source=source,
        fill_color='#fd79a8', line_color=None,
        hover_fill_color='#ff99cc', hover_line_color='#fd79a8'
    )

    # Style the chart
    p.grid.grid_line_color = None
    p.outline_line_color = None
    text_color = '#dfe6e9'
    
    # Apply text styling
    for element in [p.title, p.xaxis.axis_label, p.yaxis.axis_label]:
        if element: element.text_color = text_color
    for axis in [p.xaxis, p.yaxis]:
        axis.major_label_text_color = text_color
    
    # Additional styling
    p.xaxis.major_label_orientation = 0.7
    p.yaxis.formatter = NumeralTickFormatter(format="0,0")
    p.title.text_font_size = '16pt'
    p.toolbar.logo = None
    p.toolbar.autohide = True

    # Save as HTML file
    output_html = output_path.rsplit('.', 1)[0] + '.html'
    with open(output_html, 'w') as f:
        f.write(file_html(p, CDN, "Chat Statistics"))

def save_user_list_to_file(message_count: pd.Series, filename: str):
    try:
        grouped = message_count.groupby(message_count).apply(lambda x: x.index.tolist()).to_dict()
        sorted_grouped = dict(sorted(grouped.items(), key=lambda item: item[0], reverse=True))

        with open(filename, 'w', encoding='utf-8') as file:
            for count, users in sorted_grouped.items():
                if len(users) == 1:
                    line = f"<li>{users[0]}: {count} messages</li>\n"
                elif len(users) == 2:
                    line = f"<li>{users[0]} and {users[1]}: {count} messages each</li>\n"
                else:
                    users_str = ', '.join(users[:-1]) + f" and {users[-1]}"
                    line = f"<li>{users_str}: {count} messages each</li>\n"
                file.write(line)
    except Exception as e:
        logging.error(f"Error writing to file {filename}: {str(e)}")

def count_emote_usage(chat_df: pd.DataFrame, emotes: List[str]) -> pd.Series:
    emote_counts = {emote: chat_df['message'].apply(lambda x: x.count(emote)).sum() for emote in emotes}
    return pd.Series(emote_counts)

def append_totals_to_file(message_count_per_user: pd.Series, filename: str):
    with open(filename, 'a', encoding='utf-8') as file:
        file.write(f"\nTotal Messages Sent: {message_count_per_user.sum()}\n")
        file.write(f"Total Participants: {len(message_count_per_user)}\n")

def save_emote_usage_to_file(emote_usage: Dict[str, int], filename: str):
    try:
        with open(filename, 'w', encoding='utf-8') as file:
            for emote, count in emote_usage.items():
                file.write(f"{emote}: {count}\n")
    except Exception as e:
        logging.error(f"Error writing to file {filename}: {str(e)}")

def process_streamer_data(streamer_path: str):
    """Process chat data for a single streamer."""
    logging.info(f"Processing data for streamer: {streamer_path}")
    
    # Create output directories if they don't exist
    output_dir = os.path.join(streamer_path)
    html_dir = os.path.join(streamer_path, 'html')
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(html_dir, exist_ok=True)

    # Get all txt files in the streamer directory
    file_paths = glob.glob(os.path.join(streamer_path, '*.txt'))
    if not file_paths:
        logging.warning(f"No chat files found in {streamer_path}")
        return

    chat_df = concatenate_dfs(file_paths)
    chat_df['timestamp'] = pd.to_datetime(chat_df['timestamp'], format="%H:%M:%S", errors='coerce')

    message_count_per_user = analyze_data(chat_df)
    top_users = message_count_per_user.head(TOP_USERS_COUNT)
    
    # Save visualization with streamer-specific filename
    visualize_top_users(top_users, os.path.join(output_dir, 'top_users.png'))
    
    emotes = ["oblivi118WINK", "oblivi118Lighter", "oblivi118Hands", "oblivi118Gun",
              "oblivi118Cozy", "oblivi118Cookie", "oblivi118Lurking", "oblivi118Giggle",
              "oblivi118Sip", "oblivi118Pat", "oblivi118Sing", "oblivi118Heart",
              "oblivi118Blush", "oblivi118Huh", "oblivi118Lol", "oblivi118Hehe",
              "oblivi118What", "oblivi118Evil", "oblivi118Zzz", "oblivi118Tea"]
    emote_usage = count_emote_usage(chat_df, emotes)
    
    # Save files in streamer-specific directory
    save_user_list_to_file(message_count_per_user, os.path.join(output_dir, 'user_message_counts.txt'))
    append_totals_to_file(message_count_per_user, os.path.join(output_dir, 'user_message_counts.txt'))
    
    sorted_emote_usage = dict(sorted(emote_usage.items(), key=lambda item: item[1], reverse=True))
    save_emote_usage_to_file(sorted_emote_usage, os.path.join(output_dir, 'emote_usage.txt'))
    
    for user in TARGET_USERS:
        count = message_count_per_user.get(user.lower(), 0)
        logging.info(f"Final count for {user}: {count}")
    
    # Process HTML files for this streamer
    sanitise.modify_html_files(html_dir)

def main():
    # Get all streamer directories in chattrans
    streamer_dirs = [d for d in glob.glob('chattrans/*') if os.path.isdir(d)]
    
    if not streamer_dirs:
        logging.warning("No streamer directories found in chattrans/")
        return

    for streamer_dir in streamer_dirs:
        process_streamer_data(streamer_dir)

if __name__ == "__main__":
    main()


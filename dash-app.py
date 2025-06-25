import os
from dash import Dash, dcc, html, Input, Output, no_update
from dash.exceptions import PreventUpdate
from dash.dependencies import Input, Output
import plotly.express as px
import pandas as pd
from datetime import datetime, time

import threading
import logging
import pytz

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Global DataFrame and metadata for thread-safe storage
global_data = {
    "df": None, #pd.DataFrame(),
    "df_timestamp": 0,
    "last_updated": None
}
lock = threading.Lock()

app = Dash(__name__)
app.layout = html.Div([
    html.H1("Options Chain Dashboard", style={'textAlign': 'center'}),
    html.Div(id='df-updated', style={'display': 'none'}), # Hidden div to pass data
    dcc.Graph(id='volume-graph'),
    dcc.Graph(id='pez-graph'),
    dcc.Interval(id='interval-component', interval=60*1000, n_intervals=0)  # Update every 60 seconds
])

def df_transform(df: pd.DataFrame) -> pd.DataFrame:
    df.sort_values(['symbol', 'created_at'], inplace=True)
    df['day_volume'] = df.day_volume.fillna(0)
    gb = df.groupby('symbol')
    df['volume'] = gb['day_volume'].diff().fillna(0)
    df['eastern_tz'] = df['created_at'].dt.tz_convert('US/Eastern')

    today_eastern = datetime.now(pytz.timezone('US/Eastern')).date()
    today_eastern = df.eastern_tz.max()
    cutoff_time = time(9, 30, 0)
    cutoff_timestamp_eastern = pd.Timestamp(
        datetime.combine(today_eastern, cutoff_time),
        tz='US/Eastern'
    )
    df = df[df['eastern_tz'] >= cutoff_timestamp_eastern]

    return df


@app.callback(
    Output('df-updated', 'children'),
    Output('interval-component', 'interval'),
    Input('interval-component', 'n_intervals')
)
def update_graph(n_intervals):
    """
    Updates the FOO and the interval for refreshing the data.

    This callback function is triggered by a periodic interval component. It checks
    if the underlying data file has been modified
    since the last check. If the file has been updated, it reloads the DataFrame,
    transforms it, and updates the global data store. It also adjusts the
    refresh interval for the 'interval-component' based on the age of the data
    file.

    Args:
        n_intervals (int): The number of times the 'interval-component' has fired.
                           Used to force an update on the initial load (n_intervals == 0).

    Returns:
        tuple: A tuple containing:
            - str or dash.no_update: 'df-updated' if the DataFrame was updated,
                                     'sure' on initial load, otherwise `dash.no_update`.
                                     This value is assigned to the 'children'
                                     property of 'df-updated' (likely a dummy component
                                     to trigger other callbacks dependent on data updates).
            - int: The next interval in milliseconds for the 'interval-component'.
                   This is dynamically adjusted based on the timestamp of the data file.
    """
    update = no_update
    df = global_data["df"]
    # Access global DataFrame
    with lock:
        try:
            filename = './SPY.2025-06-24.chain.parquet'
            df_timestamp = int(os.path.getmtime(filename))
            logger.debug(f"filename={filename} df_timestamp={df_timestamp}")
            if global_data["df_timestamp"] != df_timestamp:
                update = 'df-updated'
                global_data["df_timestamp"] = df_timestamp
                df = pd.read_parquet(filename)
                if df.empty:
                    logger.warning("No data available for graph")
                    return (no_update, 300_000)
                df = df_transform(df)
                global_data["df"] = df
                logger.info(f"Loaded {filename}")
            else:
                logger.info(f"Loaded {filename} -- NOOP")
        except FileNotFoundError:
            logger.error(f"Data file not found: {filename}")
            return (no_update, 300_000)
        except Exception as e:
            logger.error(f"SOL exception: {e}")
                                                 
    if n_intervals == 0:
        update = 'initial-load'

    max_t = df.eastern_tz.max()
    now_t = int(datetime.now().timestamp())
    age_t = now_t - global_data["df_timestamp"]
    if age_t < 60:
        next_interval = age_t * 1000
    if age_t > 60 and age_t < 300:
        next_interval = 5000
    if age_t > 300:
        next_interval = 60_000 * 20
    logger.info(f"now_t={now_t} age_t={age_t} next_interval={next_interval} max_t={max_t}")
    return (update, next_interval)

@app.callback(
    Output('volume-graph', 'figure'),
    Input('df-updated', 'children'),
)
def update_graph(intermediate_data):
    df = global_data["df"]
    if df.empty:
        logger.warning(f"No data available for Daily Volume graph {intermediate_data}")
        return px.bar(title="No data available for Daily Volume graph")
    #data = df[(df.created_at == df.created_at.max()) & (df.putCall == 'CALL') ].copy()
    data = df[(df.created_at == df.created_at.max()) ]
    fig = px.bar(data, x='strike', y='day_volume', color='putCall', barmode='group', title=f"Volume by Strike Price {df.eastern_tz.max().strftime('%Y-%m-%d %H:%M')}")
    fig.update_layout(xaxis_title="Strike Price", yaxis_title="Volume")
    tmp = data.underlyingPrice.mean()
    fig.add_vline(x=tmp, annotation_text=f'Last {tmp}', line_color='crimson')
    logger.info(f"Returning Daily Volume graph")
    return fig

@app.callback(
    Output('pez-graph', 'figure'),
    Input('df-updated', 'children'),
)
def update_graph(intermediate_data):
    if intermediate_data is None:
        raise PreventUpdate
    df = global_data["df"]
    if df.empty:
        logger.warning("No data available for pez-graph")
        return px.bar(title="No data available for pez-graph")
    data = df[ (df.putCall == 'CALL') & (df.volume > 500) & (df.volume < 15000) ]
    fig = px.scatter(data, x='eastern_tz', y='volume', color='symbol', title="Volume by Strike Price")
    fig.update_layout(xaxis_title="Strike Price", yaxis_title="Volume", template='plotly_dark')
    fig.update_xaxes(tickformat="%H:%M")
    return fig

# Run Dash app
if __name__ == '__main__':
    logger.info('Starting')
    app.run(debug=True, host='127.0.0.1', port=8050)
    logger.info('Done')


# CS621-sentiment_analysis
YouTube sentiment analysis for college football YouTubers: reaction to the College Football Playoff's 24-team expansion announcement (Nov 9, 2026), comparing Josh Pate's College Football Show and Crain & Cone.

## Setup
```bash
pip install -r requirements.txt
echo "YOUTUBE_API_KEY=your_key" > .env    # gitignored
```

## Pipeline
| Step | File | Output |
|---|---|---|
| Collection | `collect.py` (`verify`, `candidates`, `comments`, `countries`) | `data/raw/*.json`, `data/commenter_channels.json` |
| Ingestion | `notebooks/01_ingestion.ipynb` | `data/comments_raw.csv` (raw dataset) |
| Cleaning | `notebooks/02_cleaning.ipynb` | `data/comments_clean.csv` (cleaned dataset) |
| Basic analytics | `notebooks/03_basic_analytics.ipynb` | figures |
| Sentiment | `notebooks/04_sentiment.ipynb` | `data/comments_scored.csv`, `data/tool_failure_patterns.csv` (after hand labeling) |
| Event study | `notebooks/05_event_study.ipynb` | `data/event_study_results.csv`, figures |
| Fan-base analysis | `notebooks/06_fanbase_spatial.ipynb` | `data/comment_teams.csv`, `data/team_sentiment.csv`, figures |
| Emoji | `notebooks/07_emoji.ipynb` | `data/comment_emoji.csv`, figures |
| Creator comparison | `notebooks/08_creator_comparison.ipynb` | `data/headline_numbers.csv`, figures, figure index |

Run the notebooks in order; each reads the previous step's CSV. Figures are saved to `figures/`. Settings shared by all steps (announcement time, channels, paths) are in `config.py`.

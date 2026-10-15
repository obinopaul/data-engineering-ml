# Streamlit

From `main/`, use the same environment:

```bash
source .venv/bin/activate
streamlit run Streamlit/app.py
```

Open the displayed URL and choose your own CSV or Parquet file. `app.py` displays it as a DataFrame. Add task-specific charts or analysis after `st.dataframe(frame)`. The file is read into memory.

Adapted from [Streamlit's DataFrame demo](https://github.com/streamlit/streamlit/blob/develop/lib/streamlit/hello/dataframe_demo.py), with upload replacing the external sample dataset.

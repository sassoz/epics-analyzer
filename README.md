# **JIRA Business Epic Analyzer & Reporter**

A comprehensive tool that automates extraction, analysis, visualization, and reporting for JIRA Business Epics. This project pulls JIRA issues, performs a deep multi-stage analysis, and generates detailed HTML reports that include both quantitative metrics and AI-powered qualitative summaries.

## **Features**

* **Automated JIRA Extraction**: Logs into JIRA and recursively extracts raw data from Business Epics and all linked issues.
* **Modular Metric Analysis**: Runs specialized analyses across several domains:

  * **Scope Analysis**: Assesses scope, complexity, and the distribution of work across teams/Jira projects.
  * **Status Analysis**: Calculates time spent in each status as well as total cycle time (“Coding Time”).
  * **Time Creep Analysis**: Detects and evaluates schedule slippage on target dates and fix versions using an LLM.
  * **Backlog Analysis**: Visualizes how the active story backlog evolves over time (added vs. completed).
* **AI-Assisted Content Summaries**: Uses an LLM to turn raw data into a clear, business-oriented epic summary.
* **Hierarchy & Data Visualization**:

  * Automatically builds tree diagrams of the issue hierarchy with GraphViz.
  * Generates plots for backlog trends.
* **Intelligent HTML Reporting**: Merges all analysis metrics and qualitative summaries into a single data object and uses an LLM to produce a formatted, easy-to-read HTML report.
* **Automated Translation**: Translates generated German HTML reports into English with a specialized LLM while preserving domain terminology.
* **Flexible Configuration & Control**: Easily configure JIRA access, LLM models, and script behavior via a config file, environment variables, and command-line arguments.

## **Analysis Workflow**

The process is split into several logical steps to ensure high data quality and reproducible results:

1. **Data Collection (`jira_scraper.py`)**: Extracts raw data for the specified JIRA epics and all linked issues, storing them as individual JSON files.
2. **Data Preparation (`project_data_provider.py`)**: Loads raw data for an epic, builds a dependency tree, and centrally provides all relevant information (details, activities) to the analysis modules.
3. **Metric Analysis (`features/*_analyzer.py`)**: The `AnalysisRunner` executes each specialized analyzer. Each analyzer processes data from the `ProjectDataProvider` and returns a structured result with its specific metrics.
4. **Content Analysis (`main_scraper.py`)**: An LLM is used to create a qualitative summary from the JIRA ticket content.
5. **Visualization (`jira_tree_classes.py`, `console_reporter.py`)**: In parallel, hierarchy graphs and backlog charts are generated as image files.
6. **Synthesis (`json_summary_generator.py`)**: Results from **all** metric analyses (step 3) and the content analysis (step 4) are merged into a single, comprehensive JSON file (`*_complete_summary.json`).
7. **Report Generation (`epic_html_generator.py`)**: This final JSON file serves as context for another LLM, which uses an HTML template to generate the final, formatted report and embed the previously created visualizations.
8. **Translation (`html_translator.py`)**: (Optional) The generated German HTML report is read, all text content is extracted, and sent in a single batch call to an LLM for translation into English.

## **Quick Start**

1. **Clone and install the repository:**

   ```bash
   git clone <repository_url>
   cd jira-business-epic-analyzer
   pip install -r requirements.txt
   ```

2. **Set environment variables:**
   Create a `.env` file in the project root and add your Azure AI credentials:

   ```
   AZURE_OPENAI_API_KEY="YOUR_OPENAI_API_KEY"
   AZURE_OPENAI_API_VERSION="YOUR_API_VERSION"
   AZURE_OPENAI_ENDPOINT="YOUR_OPENAI_ENDPOINT"

   AZURE_AIFOUNDRY_API_KEY="YOUR_AIFOUNDRY_API_KEY"
   AZURE_AIFOUNDRY_ENDPOINT="YOUR_AIFOUNDRY_ENDPOINT"
   ```

3. **Define JIRA issues:**
   Create a text file (e.g., `BE_Liste.txt`) and add the JIRA Business Epic keys (one per line).

4. **Run the script:**

   ```bash
   python src/main_scraper.py --file BE_Liste.txt --scraper check --html_summary true --translate check
   ```

5. **Review results:**
   Generated artifacts are in the `data` directory:

   * `data/html_reports/`: Final HTML reports (German and English versions).
   * `data/issue_trees/`: PNG visualizations of hierarchies.
   * `data/json_summary/`: Final merged JSON reports.
   * `data/jira_issues/`: Raw JSON data from JIRA.
   * `data/plots/`: Generated charts (e.g., backlog evolution).

## **CLI Reference**

The script is controlled via `src/main_scraper.py`:

| Argument         | Type             | Default | Description                                                                                                                                                                                                   |
| :--------------- | :--------------- | :------ | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `--scraper`      | true/false/check | check   | **true**: Force re-scraping all data. <br> **false**: Skip scraping entirely. <br> **check**: Only scrape issues whose local files are outdated.                                                              |
| `--html_summary` | true/false/check | false   | **true**: Force full re-analysis and HTML generation. <br> **false**: Skip analysis & reporting. <br> **check**: Use a cached analysis file (`*_complete_summary.json`) if available, otherwise analyze anew. |
| `--translate`    | true/false/check | false   | **true**: Force translation into English. <br> **false**: Skip translation. <br> **check**: Translate only if the English HTML file doesn’t exist yet.                                                        |
| `--issue`        | string           | None    | Process a single specific JIRA issue ID instead of a file.                                                                                                                                                    |
| `--file`         | string           | None    | Path to the `.txt` file with Business Epic keys. If not provided, you’ll be prompted interactively.                                                                                                           |

### **Examples**

* **Standard run (recommended)**: Re-scrape outdated data, load analysis from cache if present, regenerate HTML report.

  ```bash
  python src/main_scraper.py --file BE_Liste.txt --scraper check --html_summary check
  ```

* **Create HTML reports and translate to English**:

  ```bash
  python src/main_scraper.py --file BE_Liste.txt --html_summary check --translate check
  ```

* **Analysis and reporting only (no scraping)**:

  ```bash
  python src/main_scraper.py --file BE_Liste.txt --scraper false --html_summary true
  ```

* **Full refresh of all data and reports**:

  ```bash
  python src/main_scraper.py --file BE_Liste.txt --scraper true --html_summary true
  ```

* **Process a single Business Epic**:

  ```bash
  python src/main_scraper.py --issue BEMABU-12345 --scraper check --html_summary true
  ```

* **Token usage evaluation**:

  ```bash
  python src/utils/token_usage_class.py --time week
  ```

## **Project Structure**

The project is modular to keep responsibilities clearly separated.

```
jira-business-epic-analyzer/
├── data/
│   ├── html_reports/      # Final HTML reports
│   ├── issue_trees/       # Saved PNG hierarchies
│   ├── jira_issues/       # Raw JSON data from JIRA
│   ├── json_summary/      # Merged JSON reports
│   └── plots/             # Generated charts
├── logs/
│   └── token_usage.jsonl  # Log of LLM token usage
├── prompts/               # YAML files with LLM prompts
│   ├── ...
├── src/
│   ├── features/          # Modules for metric analysis
│   │   ├── ...
│   ├── utils/             # Utilities and clients
│   │   ├── azure_ai_client.py
│   │   ├── config.py
│   │   ├── html_translator.py   # NEW: translation module
│   │   ├── jira_scraper.py
│   │   └── ...
│   └── main_scraper.py    # Orchestrator script
├── templates/
│   └── epic-html_template.html   # HTML template for reports
├── .env                   # Environment variables (API keys, etc.)
└── README.md
```

## **Automated Translation**

The tool includes a built-in function to automatically translate generated German HTML reports into English. This process is handled by `src/utils/html_translator.py`.

### **How it works**

Translation uses an efficient **batch strategy**:

1. All text to be translated (including headings, lists, tables, and image captions) is extracted from the German HTML file.
2. This collection is sent in a single call to an LLM specialized in telecom and IT jargon.
3. The LLM returns a structured JSON object with the translations.
4. The script reinserts the English texts into the original HTML structure and saves the result as a new file (`*_summary_english.html`).

This approach ensures high speed and contextually accurate translation of domain terminology. The function is controlled via the `--translate` command-line argument.

## **Prompt Templates**

LLM instructions (prompts) are stored as external YAML files in the `prompts/` directory for easy customization. The `prompt_loader.py` module loads these templates.

* `business_value_prompt.yaml`: Defines the system prompt for extracting structured data from the “Business Value” field in JIRA during scraping.
* `summary_prompt.yaml`: Template for generating a comprehensive qualitative JSON summary of the entire issue tree (goals, features, etc.).
* `time_creep_summary.yaml`: Controls the LLM analysis of captured schedule shifts and produces a textual assessment of project dynamics.
* `html_generator_prompt.yaml`: Defines instructions for the LLM to create the full HTML report from the final merged JSON data object.

## **AI Integration & LLM Usage**

All interaction with language models is encapsulated in `src/utils/azure_ai_client.py`.

### **Central `AzureAIClient`**

The `AzureAIClient` class serves as a unified interface (wrapper) for different Azure AI services. This keeps the rest of the codebase agnostic to the specific backend used for a request. The client automatically routes requests to the correct service based on the model name provided.

### **Supported Model Families**

The client is designed to work with two main categories of Azure services:

1. **Azure OpenAI Service**: Used for powerful multimodal models like `gpt-4o` or `gpt-4.1-mini`, which can process both text and images.
2. **Azure AI Foundation Models**: Endpoint for a variety of open-source models such as Llama or Mistral, primarily optimized for text-to-text tasks.

The mapping of which model is used for which task (e.g., HTML generation, content summarization) is centrally defined in `src/utils/config.py` and can be adjusted there to test different models.

## **Logging**

The program includes robust logging configured in `src/utils/logger_config.py` to make execution traceable and debugging easier.

Two kinds of logs are written in parallel:

1. **File log (`logs/jira_scraper.log`)**: Records all events from log level INFO upward. This file contains a complete record of steps taken, including successful operations, and is useful for later analysis and debugging.
2. **Console log**: By default, only messages with log level WARNING or higher are printed to the terminal. This keeps console output concise and focused on important warnings or critical errors that may require intervention.

Additionally, a separate log file for **token usage** (`logs/token_usage.jsonl`) is maintained to provide transparent tracking of LLM call costs.

## **Configuration**

Configuration happens in two central places:

1. **`src/utils/config.py`**: Contains global configurations such as paths, default flags, and LLM model names for specific tasks (`LLM_MODEL_SUMMARY`, `LLM_MODEL_TIME_CREEP`, etc.).
2. **`.env` file**: Holds sensitive credentials (API keys, endpoints) and is automatically loaded by the application. This file should not be committed to version control.

## **Requirements**

### **Software**

* Python 3.10+
* Google Chrome browser

### **Python Libraries**

Required packages are listed in `requirements.txt`. Key ones include:

* `selenium` & `beautifulsoup4`: For web scraping.
* `openai`: Official client for Azure OpenAI.
* `pyyaml`: For loading prompt templates.
* `python-dotenv`: For loading environment variables.
* `pandas`: For data aggregation (especially backlog analysis).
* `networkx` & `matplotlib`: For building and visualizing graphs.

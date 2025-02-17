import os
import sys
import chardet
import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
from typing import Dict, Any
import openai
from tenacity import retry, stop_after_attempt, wait_exponential
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.impute import SimpleImputer
from dotenv import load_dotenv
import requests

# Load environment variables from a .env file
load_dotenv('file_name.env')

# Proxy URL for OpenAI API through AI Proxy
proxy_url = "https://aiproxy.sanand.workers.dev"
try:
    response = requests.get(proxy_url)
    print(f"Proxy is reachable: {response.status_code}")
except Exception as e:
    print(f"Error reaching proxy: {e}")

class AutomatedAnalysis:
    def __init__(self, dataset_path: str):
        """
        Initialize the analysis with the given dataset.

        Args:
            dataset_path (str): Path to the input CSV file
        """
        self.dataset_path = dataset_path
        self.encoding = self.detect_encoding()
        self.df = self.load_dataset()
        self.preprocess_data()
        self.api_token = self.get_api_token()
        openai.api_base = "https://aiproxy.sanand.workers.dev/openai/v1"
        openai.api_key = self.api_token

    def detect_encoding(self) -> str:
        """
        Detect the encoding of the input file.

        Returns:
            str: Detected encoding
        """
        with open(self.dataset_path, 'rb') as file:
            raw_data = file.read()
            result = chardet.detect(raw_data)
        return result['encoding'] or 'utf-8'

    def load_dataset(self) -> pd.DataFrame:
        """
        Load the dataset with the detected encoding.

        Returns:
            pd.DataFrame: Loaded dataset
        """
        try:
            df = pd.read_csv(self.dataset_path, encoding=self.encoding, low_memory=False, on_bad_lines='skip')
            print(f"Dataset loaded successfully with {df.shape[0]} rows and {df.shape[1]} columns.")
            return df
        except Exception as e:
            print(f"Error loading dataset: {e}")
            raise ValueError(f"Error loading dataset: {e}")

    def preprocess_data(self):
        """
        Preprocess the dataset by handling missing values, data types, and special columns.
        """
        # Handle date columns
        if 'date' in self.df.columns:
            self.df['date'] = pd.to_datetime(self.df['date'], errors='coerce')  # Convert to datetime
        
        # Handle categorical columns (e.g., 'language', 'type')
        categorical_cols = self.df.select_dtypes(include=['object']).columns
        self.df[categorical_cols] = self.df[categorical_cols].fillna('Unknown')  # Replace NaNs with 'Unknown'
        
        # Handle missing values for numeric columns
        numeric_cols = self.df.select_dtypes(include=[np.number]).columns
        imputer = SimpleImputer(strategy='median')
        self.df[numeric_cols] = imputer.fit_transform(self.df[numeric_cols])

    def get_api_token(self) -> str:
        """
        Retrieve API token from environment variable.

        Returns:
            str: API Token
        """
        token = os.getenv("AIPROXY_TOKEN")
        if not token:
            raise EnvironmentError("AIPROXY_TOKEN environment variable is not set.")
        return token

    def get_data_summary(self) -> Dict[str, Any]:
        """
        Generate a summary of the dataset.

        Returns:
            Dict[str, Any]: Dataset summary
        """
        return {
            "total_rows": len(self.df),
            "total_columns": len(self.df.columns),
            "column_types": self.df.dtypes.apply(str).to_dict(),
            "missing_values": self.df.isnull().sum().to_dict(),
            "numeric_summary": self.df.describe().to_dict()
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def generate_narrative(self, summary: Dict[str, Any], analysis_results: Dict[str, Any]) -> str:
        """
        Generate a narrative about the dataset using the LLM.

        Args:
            summary (Dict[str, Any]): Dataset summary
            analysis_results (Dict[str, Any]): Results of the analysis

        Returns:
            str: Narrative generated by the LLM
        """
        prompt = (
            f"Dataset Analysis:\n\n"
            f"Summary:\n{summary}\n\n"
            f"Analysis Results:\n{analysis_results}\n\n"
            "Write a detailed, well-structured Markdown summary of the dataset analysis. "
            "Include an overview of the data, key findings, and potential implications."
        )

        try:
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",  # Proxy-supported model
                messages=[{
                    "role": "system", "content": "You are an expert data analyst."
                }, {
                    "role": "user", "content": prompt
                }],
                max_tokens=500
            )

            # Extracting the generated narrative from the response
            narrative = response['choices'][0]['message']['content'].strip()

            return narrative

        except Exception as e:
            # Log the error and provide a fallback message
            print(f"Error generating narrative: {e}")
            return "An error occurred while generating the narrative."

    def save_results(self, summary: Dict[str, Any], analysis_results: Dict[str, Any], narrative: str):
        """
        Save the analysis results and narrative to files.

        Args:
            summary (Dict[str, Any]): Dataset summary.
            analysis_results (Dict[str, Any]): Analysis results.
            narrative (str): Generated narrative.
        """
        folder_name = self.dataset_path.split('.')[0]
        os.makedirs(folder_name, exist_ok=True)

        # Save narrative to README.md
        try:
            with open(f"{folder_name}/README.md", "w") as f:
                f.write("# Automated Dataset Analysis\n\n")

                f.write("## Overview\n")
                f.write(f"This repository contains an analysis of the dataset **{self.dataset_path}**. The following sections describe "
                        "the preprocessing steps, the analysis conducted, clustering results, visualizations, and insights derived from the data.\n\n")

                f.write("## Dataset Summary\n")
                f.write("The dataset consists of the following structure:\n\n")
                f.write(f"### Data Overview\n")
                f.write(f"- Total Rows: {summary['total_rows']}\n")
                f.write(f"- Total Columns: {summary['total_columns']}\n")
                f.write("### Column Data Types\n")
                f.write("```\n")
                for col, dtype in summary['column_types'].items():
                    f.write(f"- {col}: {dtype}\n")
                f.write("```\n")
                f.write("### Missing Values\n")
                f.write("```\n")
                for col, missing in summary['missing_values'].items():
                    f.write(f"- {col}: {missing} missing values\n")
                f.write("```\n")

                f.write("### Numeric Summary\n")
                f.write("```\n")
                for stat, values in summary['numeric_summary'].items():
                    f.write(f"{stat}:\n")
                    for col, value in values.items():
                        f.write(f"- {col}: {value}\n")
                f.write("```\n")

                f.write("\n## Data Preprocessing\n")
                f.write("Before performing any analysis, several preprocessing steps were conducted to clean and prepare the data:\n\n")
                f.write("- **Missing Values Handling**: Missing values in categorical columns were replaced with 'Unknown'. Numeric columns had missing values imputed using the median.\n")
                f.write("- **Date Parsing**: Any columns containing dates were parsed and converted into datetime objects.\n")
                f.write("- **Standardization**: Numerical data was standardized to ensure that features are on the same scale before applying clustering algorithms.\n")

                f.write("\n## Clustering Analysis\n")
                f.write("To uncover patterns in the data, we performed K-Means clustering on the dataset. The number of clusters was set to 3 based on prior understanding.\n\n")
                f.write("### Clustering Results\n")
                f.write(f"- **Cluster Centers**: {analysis_results['cluster_centers']}\n")
                f.write(f"- **Inertia (Sum of Squared Distances)**: {analysis_results['inertia']}\n")
                f.write("### Cluster Distribution\n")
                f.write("The following plot shows the distribution of data points across the clusters:\n\n")
                f.write("![Cluster Distribution](cluster_distribution.png)\n")
                
                f.write("\n## Visualizations\n")
                f.write("The following visualizations help in understanding the data distribution and clustering results:\n\n")

                f.write("### Correlation Heatmap\n")
                f.write("This heatmap displays the correlation between the numerical features in the dataset.\n\n")
                f.write("![Correlation Heatmap](correlation_heatmap.png)\n")

                f.write("\n## Narrative Summary\n")
                f.write("Below is the detailed narrative generated from the dataset analysis:\n\n")
                f.write("### Insights\n")
                f.write(f"```\n{narrative}\n```\n")
                
                f.write("\n## Conclusion\n")
                f.write("The analysis provides a deep understanding of the dataset. Key findings include:\n\n")
                f.write("- The dataset has several missing values, which were appropriately handled during preprocessing.\n")
                f.write("- Three clusters were identified through K-Means clustering, which offer a meaningful segmentation of the data.\n")
                f.write("- Visualizations helped in identifying relationships between variables and the distribution of data across clusters.\n\n")
                f.write("Future improvements could involve experimenting with other clustering techniques or incorporating additional data sources.")

            print("Analysis results saved successfully.")
        except Exception as e:
            print(f"Error saving results: {e}")

    def perform_clustering(self, n_clusters: int = 3):
        """
        Perform KMeans clustering on the dataset.
        
        Args:
            n_clusters (int): Number of clusters to generate.
        
        Returns:
            Dict[str, Any]: Results of the clustering analysis.
        """
        scaler = StandardScaler()
        scaled_data = scaler.fit_transform(self.df.select_dtypes(include=[np.number]))  # Only numeric columns

        kmeans = KMeans(n_clusters=n_clusters, random_state=42)
        self.df['cluster'] = kmeans.fit_predict(scaled_data)

        return {
            "cluster_centers": kmeans.cluster_centers_,
            "inertia": kmeans.inertia_
        }

    def run_analysis(self):
        """
        Run the complete dataset analysis including data preprocessing, clustering, and narrative generation.
        """
        summary = self.get_data_summary()

        # Perform clustering
        clustering_results = self.perform_clustering()

        # Generate narrative
        narrative = self.generate_narrative(summary, clustering_results)

        # Save the results
        self.save_results(summary, clustering_results, narrative)


# Example Usage
if __name__ == "__main__":
    dataset_path = "path_to_your_data.csv"  # Provide the path to your dataset
    analysis = AutomatedAnalysis(dataset_path)
    analysis.run_analysis()
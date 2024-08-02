import os
import json
import uuid
import pandas as pd
from importlib import resources as pkg_resources

from openfactcheck.lib.logger import logger
from openfactcheck.core.base import OpenFactCheck
from openfactcheck.evaluator.llm.evaluate_snowballing import SnowballingEvaluator
from openfactcheck.evaluator.llm.evaluate_selfaware import SelfAwareEvaluator
from openfactcheck.evaluator.llm.evaluate_freshqa import FreshQAEvaluator
from openfactcheck.evaluator.llm.evaluate_freetext import FreeTextEvaluator
from openfactcheck.evaluator.llm.report import create_report

from openfactcheck import data as data_dir

# Import LLM Evaluation Dataset
default_dataset_path = str(pkg_resources.files(data_dir))
default_output_path = "tmp/output/llm_evaluator"

class LLMEvaluator(SnowballingEvaluator, SelfAwareEvaluator, FreshQAEvaluator, FreeTextEvaluator):
    """
    This class is used to evaluate the performance of a Language Model.

    Parameters
    ----------
    model_name : str
        The name of the Language Model.
    input_path : Union[str, pd.DataFrame]
        The path to the CSV file or the DataFrame containing the LLM responses.
        The CSV file should have the following two columns:
        - index: The index of the response.
        - response: The response generated by the LLM.
    output_path : str
        The path to store the output files.
    dataset_path : str
        The path to the dataset file containing the questions.
    datasets : list
        The list of datasets to evaluate the LLM on. 
    analyze : bool
        Whether to analyze the results.
    save_plots : bool
        Whether to save the plots.
    save_report : bool
        Whether to save the report.

    Attributes
    ----------
    model_name : str
        The name of the Language Model.
    run_id : str
        The unique identifier for the run.
    input_path : Union[str, pd.DataFrame]
        The path to the CSV file or the DataFrame containing the LLM responses.
    output_path : str
        The path to store the output files.
    dataset_path : str
        The path to the dataset file containing the questions.
    datasets : list
        The list of datasets to evaluate the LLM on.
    combined_result : dict
        The combined evaluation results for all datasets.

    Methods
    -------
    evaluate(model_name: str, input_path: Union[str, pd.DataFrame], output_path: str = "", dataset_path: str = "", datasets: list = ["snowballing"], analyze: bool = True, save_plots: bool = True, save_report: bool = True):
        This function evaluates the performance of the Language Model.
    read_input():
        This function reads the input file and dataset file and returns a DataFrame containing the combined data.
    filter_responses(df: pd.DataFrame, dataset: str):
        Filter the responses based on the dataset.
    generate_plots(fig_path, save_plots=True):
        Generate plots for the evaluation
    """
    def __init__(self, ofc: OpenFactCheck):
        SnowballingEvaluator.__init__(self)
        SelfAwareEvaluator.__init__(self)
        FreshQAEvaluator.__init__(self)
        FreeTextEvaluator.__init__(self, ofc)
        self.logger = logger

        # Set the attributes
        self.model_name = None
        self.run_id = str(uuid.uuid4().hex)
        self.input_path = None
        self.dataset_path = None
        self.output_path = None
        self.datasets = None

        self.combined_result = None
        self.labels = None
        self.predictions = None

        self.logger.info(f"LLM Evaluator initialized with run_id: {self.run_id}")

    def read_input(self):
        """
        This function reads the input file and dataset file and returns a DataFrame containing the combined data.
        """

        # Check if the input_path is a DataFrame
        if isinstance(self.input_path, pd.DataFrame):
            df_responses = self.input_path
        else:
            # Read the CSV file
            self.logger.info(f"Reading the LLM responses from {self.input_path}...")
            df_responses = pd.read_csv(self.input_path)

        # Check the number of columns and if any response is missing
        assert df_responses.shape[1] == 2, "The LLM responses should have 2 columns."

        # Use the first column as index and rename the index and response column
        df_responses.set_index(df_responses.columns[0], inplace=True)
        df_responses.index.name = None
        df_responses.columns = ["response"]

        # Read the avaliable datasets
        self.logger.info(f"Reading the dataset from {self.dataset_path}...")
        df_dataset = pd.DataFrame()
        # Loop through each file in the directory
        for filename in os.listdir(self.dataset_path):
            if filename.endswith('.jsonl'):  # Check if the file is a JSONL file
                file_path = os.path.join(self.dataset_path, filename)

                logger.info(f"Reading {filename.split('.')[0]} dataset...")
                # Read the JSONL file and append it to the combined DataFrame
                df = pd.read_json(file_path, lines=True)
                df_dataset = pd.concat([df_dataset, df], ignore_index=True)

        # Combine the responses and questions
        assert len(df_responses) == len(df_dataset), "The number of responses and questions should be the same."
        df_combined = pd.concat([df_dataset, df_responses], axis=1)

        return df_combined       

    @staticmethod
    def filter_responses(df: pd.DataFrame, dataset: str):
        logger.info(f"Filtering responses for dataset: {dataset}...")
        # Filter the DataFrame based on the 'source' column directly
        if dataset == "snowballing":
            # Filter the DataFrame based on the 'source' column directly
            filtered_df = df[df['source'] == dataset]
            
            # Create a new DataFrame with only the required columns
            responses_df = filtered_df[['topic', 'response']].copy()
            
            # Convert the DataFrame to a list of dictionaries if needed
            responses = responses_df.to_dict(orient='records')

        elif dataset == "selfaware":
            selfaware_subset = [
                "selfaware-hotpot_train",
                "selfaware-squadqa_train",
                "selfaware-triviaqa_train",
                "selfaware-squadqa_dev",
                "selfaware-hotpot_dev",
                "selfaware-triviaqa_dev",
                "selfaware-SelfAware",
            ]

            responses = []
            for k, row in df.iterrows():
                if row["source"] in selfaware_subset:
                    responses.append({
                        "label_unanswerable": row["ability_to_test"].lstrip("answerable: ") == "False",
                        "response": row["response"]})
                    
        elif dataset == "freshqa":
            responses = []
            for k, row in df.iterrows():
                if row["source"] == dataset:
                    responses.append(
                        {
                            "question": row["question"],
                            "reference_answer": row["reference_answer"],
                            "response": row["response"],
                        }
                    )
        
        elif dataset in ["factoolqa", "felm-wk", "factcheck-bench"]:
            responses = []
            for k, row in df.iterrows():
                if row["source"] == dataset:
                    responses.append(
                        {
                            "source": row["source"],
                            "prompt": row["prompt"],
                            "response": row["response"],
                        }
                    )

        elif dataset == "factscore-bio":
            factscore_subset = [
                "factscore-labelled",
                "factscore-unlabelled",
            ]

            responses = []
            for k, row in df.iterrows():
                if row["source"] in factscore_subset:
                    responses.append(
                        {
                            "source": row["source"],
                            "prompt": row["prompt"],
                            "response": row["response"],
                        }
                    )
        else:
            raise ValueError(f"Dataset {dataset} is not supported.")
        
        return responses
    
    def generate_plots(self, fig_path: str = "", save_plots=True):
        # Create a bar plot of the accuracy of the LLM responses on the Snowballing dataset
        # for each topic and the overall accuracy.
        plots = {}
        for dataset in self.combined_result:
            if dataset == "snowballing":
                plots["snowballing"] = {}
                plots["snowballing"]["barplot"] = self.snowballing_barplot(self.combined_result[dataset], fig_path, save=save_plots)
                plots["snowballing"]["cm"] = self.snowballing_cm(self.labels[dataset], self.predictions[dataset], fig_path, save=save_plots)

            elif dataset == "selfaware":
                plots["selfaware"] = {}
                plots["selfaware"]["barplot"] = self.selfaware_barplot(self.combined_result[dataset], fig_path, save=save_plots)
                plots["selfaware"]["cm"] = self.selfaware_cm(self.labels[dataset], self.predictions[dataset], fig_path, save=save_plots)
            
            elif dataset == "freshqa":
                plots["freshqa"] = {}
                plots["freshqa"]["piechart"] = self.freshqa_piechart(self.combined_result[dataset], fig_path, save=save_plots)

            elif dataset == "freetext":
                plots["freetext"] = {}
                plots["freetext"]["barplot"] = self.freetext_barplot(self.combined_result["freetext"], fig_path, save=save_plots)

        return plots
    
    def generate_report(self, report_path: str):
        # Create a LaTeX report and return the path to the generated PDF
        return create_report(self.model_name, report_path)

    def evaluate(self, 
                 model_name: str,
                 input_path: str, 
                 output_path: str = "",
                 dataset_path: str = "", 
                 datasets: list = [
                     "snowballing",
                     "selfaware",
                     "freshqa",
                     "factoolqa",
                     "felm-wk",
                     "factcheck-bench",
                     "factscore-bio"
                 ],
                 analyze: bool = True,
                 save_report: bool = True):
        self.logger.info("Evaluating LLM responses...")

        # Set the attributes
        self.model_name = model_name
        self.input_path = input_path
        self.output_path = output_path
        self.dataset_path = dataset_path
        self.datasets = datasets
        
        # Check if the output path is provided (if not, use the default template)
        if self.output_path == "":
            self.output_path = default_output_path

        # Check if the output path exists (if not, create it)
        if not os.path.exists(f"{self.output_path}/{self.run_id}"):
            os.makedirs(f"{self.output_path}/{self.run_id}")
        
        # Check if the questions path is provided (if not, use the default template)
        if self.dataset_path == "":
            self.dataset_path = default_dataset_path

        # Read the input
        self.logger.info("Reading the input...")
        df = self.read_input()
        self.logger.info(f"Combined data contains {len(df)} rows")
        
        # Evaluate model responses over each dataset
        self.combined_result = {}
        self.labels = {}
        self.predictions = {}
        for dataset in self.datasets:
            logger.info(f"Evaluating responses for dataset: {dataset}...")
            if dataset == "snowballing":
                # Filter responses based on the dataset
                responses = self.filter_responses(df, dataset)

                # Evaluate the responses
                result, labels, preds = self.evaluate_snowballing(responses)

                # Store the output and save the results
                df_out = pd.DataFrame({"gold_labels": labels, "predictions": preds})
                df_out.to_json(f"{self.output_path}/{self.run_id}/{dataset}_output.jsonl", orient="records", lines=True)
                self.combined_result[dataset] = result
                self.labels[dataset] = labels
                self.predictions[dataset] = preds
            
            elif dataset == "selfaware":
                # Filter responses based on the dataset
                responses = self.filter_responses(df, dataset)

                # Evaluate the responses
                result, labels, preds = self.evaluate_selfaware(responses[:30])

                # Store the output and save the results
                df_out = pd.DataFrame({"gold_labels": labels, "predictions": preds})
                df_out.to_json(f"{self.output_path}/{self.run_id}/{dataset}_output.jsonl", orient="records", lines=True)
                self.combined_result[dataset] = result
                self.labels[dataset] = labels
                self.predictions[dataset] = preds

            elif dataset == "freshqa":
                # Filter responses based on the dataset
                responses = self.filter_responses(df, dataset)

                # Evaluate the responses
                result, raw_evals, preds = self.evaluate_freshqa(responses[:30])

                # Store the output and save the results
                df_out = pd.DataFrame({"raw_evaluations": raw_evals, "predictions": preds})
                df_out.to_json(f"{self.output_path}/{self.run_id}/{dataset}_output.jsonl", orient="records", lines=True)
                self.combined_result[dataset] = result

            elif dataset in ["factoolqa", "felm-wk", "factcheck-bench", "factscore-bio"]:
                # Check if the freetext key exists
                if self.combined_result.get("freetext") is None:
                    self.combined_result["freetext"] = {}

                # Filter responses based on the dataset
                responses = self.filter_responses(df, dataset)

                # Evaluate the responses
                results, evaluations = self.evaluate_freetext(responses[:30], self.model_name, self.run_id)

                # Store the output and save the results
                df_out = pd.DataFrame(evaluations)
                df_out.to_json(f"{self.output_path}/{self.run_id}/{dataset}_output.jsonl", orient="records", lines=True)
                self.combined_result["freetext"][dataset] = results
            
            else:
                logger.error(f"Dataset {dataset} is not supported.")
                raise ValueError(f"Dataset {dataset} is not supported.")

            logger.info(f"Finished evaluating responses for dataset: {dataset}")

        # save all evaluation results
        with open(f"{self.output_path}/{self.run_id}/result.json", "w") as json_file:
            json.dump(self.combined_result, json_file, indent=4)

        # Analyze the results
        if analyze:
            self.logger.info("Analyzing the results...")
            self.generate_plots(save_plots=True, fig_path=f"{self.output_path}/{self.run_id}")
        
        # Create a report
        if save_report:
            self.logger.info("Creating the report...")
            self.generate_report(report_path=f"{self.output_path}/{self.run_id}")
        
        return self.combined_result
                

        


        
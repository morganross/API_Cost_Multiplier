import asyncio
import os
import sys

# Add the process-markdown directory to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
process_markdown_path = os.path.join(current_dir, 'process-markdown')
sys.path.insert(0, process_markdown_path)

# Import necessary modules from process-markdown
import llm_doc_eval_client
import file_manager

async def main():
    print("Starting evaluation test script...")

    # Define the path to the pre-generated test reports
    test_reports_folder = os.path.abspath("./test/finaldocs")

    # Find all markdown files in the test reports folder
    test_report_paths = file_manager.find_markdown_files(test_reports_folder)

    if not test_report_paths:
        print(f"No markdown files found in the test reports folder: {test_reports_folder}. Please ensure test reports exist.")
        return

    print(f"Found {len(test_report_paths)} test reports for evaluation:")
    for path in test_report_paths:
        print(f"  - {path}")

    # Step: LLM-Doc-Eval Integration
    print("\nEvaluating generated reports using llm-doc-eval...")
    try:
        best_report_path = llm_doc_eval_client.evaluate_reports(test_report_paths)
        print(f"\nEvaluation complete. The best report is: {best_report_path}")
    except Exception as e:
        print(f"\nFailed to evaluate reports: {e}")
        print("Evaluation test script finished with errors.")
        return

    print("\nEvaluation test script finished successfully.")

if __name__ == "__main__":
    asyncio.run(main())
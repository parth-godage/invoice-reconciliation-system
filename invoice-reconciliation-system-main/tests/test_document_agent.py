from document_agent import DocumentIntelligenceAgent



def run_test(invoice_path: str):
    agent = DocumentIntelligenceAgent( tesseract_cmd="C:/Program Files/Tesseract-OCR/tesseract.exe"
)
    result = agent.process(invoice_path)

    print("\n==============================")
    print("INVOICE:", invoice_path)
    print("CONFIDENCE:", result.confidence)
    print("EXPLANATION:", result.explanation)
    print("METADATA:", result.metadata)
    print("DATA:")
    for k, v in result.data.items():
        print(f"  {k}: {v}")
    print("==============================\n")


if __name__ == "__main__":
    run_test("data/invoices/invoice1.pdf")
    run_test("data/invoices/invoice2.pdf")

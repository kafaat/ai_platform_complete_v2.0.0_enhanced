import json

def check_keys(doc):
    keys = ["required_conversation_resolution", "required_linear_history"]
    for k in keys:
        block = doc.get(k)
        if not isinstance(block, dict) or block.get("enabled") is not True:
            print(f"Missing {k}")
    
    # What about required_status_checks?
    sc = doc.get("required_status_checks")
    if not isinstance(sc, dict):
        print("Missing required_status_checks")


def onnx_providers(device: str) -> list[str]:
    if device.lower() in {"jetson_orin", "cuda", "gpu", "rtx5090", "blackwell"}:
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]

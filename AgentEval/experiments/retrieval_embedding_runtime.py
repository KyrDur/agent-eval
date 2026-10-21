"""Bound native MiniLM resources on small hosts; preserve its pooling/math."""
from functools import cached_property
from pathlib import Path
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

RESOURCE_POLICY={'inference_batch_size':1,'intra_op_threads':1,'inter_op_threads':1,
                 'cpu_memory_arena':False,'memory_pattern':False,'serialized_inference':True}

class BoundedMiniLM(ONNXMiniLM_L6_V2):
    @cached_property
    def model(self):
        options=self.ort.SessionOptions()
        options.log_severity_level=3
        options.graph_optimization_level=self.ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        options.intra_op_num_threads=RESOURCE_POLICY['intra_op_threads']
        options.inter_op_num_threads=RESOURCE_POLICY['inter_op_threads']
        options.enable_cpu_mem_arena=RESOURCE_POLICY['cpu_memory_arena']
        options.enable_mem_pattern=RESOURCE_POLICY['memory_pattern']
        return self.ort.InferenceSession(str(Path(self.DOWNLOAD_PATH)/self.EXTRACTED_FOLDER_NAME/'model.onnx'),
                                        providers=['CPUExecutionProvider'],sess_options=options)

    def _forward(self,documents,batch_size=1):
        return super()._forward(documents,batch_size=RESOURCE_POLICY['inference_batch_size'])

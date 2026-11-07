"""Research-only Russian INT8 tagger; original words are reconstructed unchanged.

CPU ONNX Runtime is an eval backend, not an accepted mobile SDK dependency.
"""
import json
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer
from native_sdk import ROOT
from scoring import normalize

class RUPunct:
    def __init__(self,threads=4):
        directory=ROOT/'models/rupunct-small-int8'
        self.tokenizer=Tokenizer.from_file(str(directory/'tokenizer.json'))
        self.config=json.loads((directory/'config.json').read_text())
        options=ort.SessionOptions();options.intra_op_num_threads=threads;options.inter_op_num_threads=1
        self.session=ort.InferenceSession(str(directory/'rupunct_small_int8.onnx'),options,providers=['CPUExecutionProvider'])

    def __call__(self,text):
        words=text.split();output=[]
        # Frozen 100-word windows; never silently truncate a long word.
        for start in range(0,len(words),100):
            chunk=words[start:start+100]
            encoded=self.tokenizer.encode(chunk,is_pretokenized=True)
            if len(encoded.ids)>self.config['max_position_embeddings']:raise ValueError('Punctuation window exceeds token limit')
            feed={name:np.array([value],dtype=np.int64) for name,value in
                  [('input_ids',encoded.ids),('attention_mask',encoded.attention_mask),('token_type_ids',encoded.type_ids)]}
            labels=self.session.run(None,feed)[0][0].argmax(axis=-1)
            first={}
            for i,word in enumerate(encoded.word_ids):
                if word is not None and word not in first:first[word]=int(labels[i])
            for i,word in enumerate(chunk):
                if i not in first:raise ValueError('Tokenizer omitted lexical word')
                label=self.config['id2label'][str(first[i])]
                mode,mark=label.rsplit('_',1)
                if mode=='UPPER':word=word.capitalize()
                elif mode=='UPPER_TOTAL':word=word.upper()
                marks={'O':'','PERIOD':'.','COMMA':',','QUESTION':'?','TIRE':' —','DVOETOCHIE':':',
                       'VOSKL':'!','PERIODCOMMA':';','DEFIS':'-','MNOGOTOCHIE':'...','QUESTIONVOSKL':'?!'}
                output.append(word+marks[mark])
        result=' '.join(output)
        if normalize(result)!=normalize(text):raise ValueError('Punctuator changed lexical content')
        return result

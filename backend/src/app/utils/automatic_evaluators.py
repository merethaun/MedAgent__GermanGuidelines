from functools import lru_cache


# also requires packages: datasets, numpy, nltk, absl-py, rouge-score, bert_score

@lru_cache(maxsize=1)
def get_rouge():  # https://huggingface.co/spaces/evaluate-metric/rouge
    import evaluate
    return evaluate.load("rouge")


@lru_cache(maxsize=1)
def get_bleu():  # https://huggingface.co/spaces/evaluate-metric/bleu
    import evaluate
    return evaluate.load("bleu")


@lru_cache(maxsize=1)
def get_meteor():  # https://huggingface.co/spaces/evaluate-metric/meteor
    import evaluate
    return evaluate.load("meteor")


@lru_cache(maxsize=1)
def get_bertscore():  # https://huggingface.co/spaces/evaluate-metric/bertscore, ASSUME GERMAN!!
    import evaluate
    return evaluate.load("bertscore")

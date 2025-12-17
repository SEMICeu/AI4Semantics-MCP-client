from typing import (
    List,
    Dict,
    Any,
)
from os import (
    getenv,
)
from datetime import (
    datetime,
)
from pandas import (
    DataFrame,
    read_excel,
    concat,
)
from tqdm import (
    tqdm,
)
from pwc_api import (
    _make_prompt,
)
from pwc_api.client import (
    Client,
)
from pwc_api.chat.vocabularies import (
    _predict_vocabularies,
)


def main() -> None:
    cc_client = Client().chat_completions
    qc: DataFrame = read_excel('tests/qa.xlsx')
    kwargs: Dict[str, Any] = {
        'model': str(getenv('LLM_MODEL')),
        'temperature': 0,
        'stream': False,
    }
    system_message: str = (
        "You are an AI assistant that answers the user's UML questions."
        "Use knowledge from the library to respond."
    )
    results: Dict[str, List[Any]] = {
        'predictions': [],
        'result': [],
    }
    for i in tqdm(range(len(qc)), desc='Predicting Vocabulary'):
        question: str = qc['question'].iloc[i]
        vocabulary: str = qc['vocabulary'].iloc[i]
        prediction: List[str] = _predict_vocabularies(
            _make_prompt(
                system_message,
                user_message=question,
            ),
            cc_client,
            kwargs,
        )
        results['predictions'].append(prediction)
        results['result'].append(
            'Passed'
            if vocabulary in prediction else
            'Failed'
        )

    for col, vals in results.items():
        qc[col] = vals

    name: str = datetime.now().strftime("%d-%m-%y_%H-%M")
    qc \
        .drop(
            'answer',
            axis=1,
        ) \
        .to_excel(
            f'tests/vocabularies/results/voc_{name}.xlsx',
            index=False,
        )

    n_error: int = sum(res == 'Failed' for res in results['result'])
    if n_error == 0:
        print('Vocabularies: all tests passed!')

    else:
        print(f'Vocabularies: {n_error}/{len(qc)} tests failed.')

    path: str = 'tests/vocabularies/results/voc_results.xlsx'
    concat(
        [
            read_excel(path),
            DataFrame(
                {
                    'name': [name],
                    'error rate': [n_error/len(qc)]
                }
            ),
        ],
        axis=0,
    ) \
        .to_excel(
            path,
            index=False,
        )

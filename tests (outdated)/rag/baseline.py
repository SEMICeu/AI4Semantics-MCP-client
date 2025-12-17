from os import (
    getenv,
)
from typing import (
    Dict,
    List,
    Any,
)
from datetime import (
    datetime,
)
from pandas import (
    DataFrame,
    Series,
    read_excel,
)
from langchain_openai import (
    ChatOpenAI,
)
from ragas import (
    evaluate,
)
from ragas.dataset_schema import (
    EvaluationResult,
    EvaluationDataset,
)
from ragas.llms import (
    LangchainLLMWrapper,
)
from ragas.metrics import (
    AnswerAccuracy,
    ContextRelevance,
    LLMContextPrecisionWithReference,
    LLMContextRecall,
    ResponseGroundedness,
    Faithfulness,

)
from openai.resources.chat.completions import (
    Completions,
)
from tqdm import (
    tqdm,
)
from pwc_api.client import (
    Client,
)
from pwc_api import (
    _make_prompt,
)
from pwc_api.chat.completions import (
    _call_regular_api,
)


def main() -> None:
    evaluator: LangchainLLMWrapper = LangchainLLMWrapper(
        ChatOpenAI(
            base_url=str(getenv('SHARED_SERVICE_OPENAI_URL')),
            api_key=str(getenv('RAG_CHATBOT_API_KEY')),  # type: ignore
            model=str(getenv('LLM_MODEL')),
            temperature=0,
        )
    )
    client: Completions = Client().chat_completions
    kwargs: Dict[str, Any] = {
        'model': 'azure.gpt-4o',
        'temperature': 0,
        'stream': False,
    }
    qa: DataFrame = read_excel('tests/qa.xlsx')
    data: List[Dict[str, Any]] = []
    uris: List[List[str]] = []
    for i in tqdm(range(len(qa)), desc='Generating answers'):
        res: Dict[str, Any] = _call_regular_api(
            _make_prompt(
                "You are an AI assistant answering the user's UML questions."
                "You help the user regarding semantic modelling."
                "Use knowledge from the library to respond.",
                qa['question'].iloc[i]
            ),
            client,
            kwargs
        )
        generated: str = res['completion'].choices[0].message.content
        # print(
        #     '',
        #     f'Q: {qa['question'].iloc[i]}',
        #     f'A: {generated}',
        #     '\n',
        #     sep='\n'
        # )

        data.append({
            'user_input': qa['question'].iloc[i],
            'retrieved_contexts': [
                doc['Content']
                for doc
                in res['docs']
            ],
            'response': generated,
            'reference': qa['answer'].iloc[i]
        })
        uris.append(
            [
                doc['uri']
                for doc
                in res['docs']
            ]
        )

    results: EvaluationResult = evaluate(
        dataset=EvaluationDataset.from_list(data),
        metrics=[
            AnswerAccuracy(),
            # AnswerCorrectness(),
            ContextRelevance(),
            LLMContextPrecisionWithReference(),
            LLMContextRecall(),
            ResponseGroundedness(),
            Faithfulness(),
        ],
        llm=evaluator,
    )

    qa_results: DataFrame = results.to_pandas()
    qa_results['uris'] = uris
    name: str = datetime.now().strftime("%d-%m-%y_%H-%M")
    path_result: str = f'tests/rag/results/rag_baseline_{name}.xlsx'
    qa_results.to_excel(
        path_result,
        index=False,
    )
    averaged_results: Dict[str, Any] = {'name': f'baseline_{name}'}
    averaged_results |= {
        metric: mean
        for metric, mean
        in results._repr_dict.items()
    }
    averaged_results['name'] = f'baseline_{name}'
    path_results: str = 'tests/rag/results/rag_results.xlsx'
    rag_results: DataFrame = read_excel(path_results)
    rag_results.iloc[0] = Series(averaged_results)
    rag_results.to_excel(
        path_results,
        index=False,
    )
    print(
        '',
        'Averaged resutls:',
        *(
            f'{metric}: {mean:.3f}'
            for metric, mean
            in results._repr_dict.items()
        ),
        sep='\n'
    )

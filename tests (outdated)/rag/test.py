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
    read_excel,
    concat,
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
    ResponseGroundedness,
    # LLMContextPrecisionWithReference,
    # LLMContextRecall,
    # Faithfulness,

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
    create,
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
        'model': str(getenv('LLM_MODEL')),
        'temperature': 0,
        'stream': False,
    }
    qa: DataFrame = read_excel('tests/qa.xlsx')
    data: List[Dict[str, Any]] = []
    titles: List[List[str]] = []
    for i in tqdm(range(len(qa)), desc='Generating answers'):
        res: Dict[str, Any] = create(
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
        titles.append(
            [
                doc['Title']
                for doc
                in res['docs']
            ]
        )

    results: EvaluationResult = evaluate(
        dataset=EvaluationDataset.from_list(data),
        metrics=[
            AnswerAccuracy(),
            ResponseGroundedness(),
            ContextRelevance(),
            # AnswerCorrectness(),
            # LLMContextPrecisionWithReference(),
            # LLMContextRecall(),
            # Faithfulness(),
        ],
        llm=evaluator,
    )

    qa_results: DataFrame = results.to_pandas()
    qa_results['titles'] = titles
    name: str = datetime.now().strftime("%d-%m-%y_%H-%M")
    path_result: str = f'tests/rag/results/rag_{name}.xlsx'
    qa_results.to_excel(
        path_result,
        index=False,
    )
    averaged_results: Dict[str, List[Any]] = {
        metric: [mean]
        for metric, mean
        in results._repr_dict.items()
    }
    averaged_results['name'] = [name]
    path_results: str = 'tests/rag/results/rag_results.xlsx'
    concat(
        [
            read_excel(path_results),
            DataFrame(averaged_results),
        ],
        axis=0,
    ) \
        .to_excel(
            path_results,
            index=False,
        )
    print(
        '',
        'Averaged results:',
        *(
            f'{metric}: {mean:.3f}'
            for metric, mean
            in results._repr_dict.items()
        ),
        sep='\n'
    )

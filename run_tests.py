if __name__ == '__main__':
    # from dotenv import load_dotenv
    from tests.vocabularies import (
        test_vocs,
    )
    from tests.rag import (
        baseline,
        test_rag,
    )
    test_vocs()
    # baseline()
    test_rag()

from rest_framework.pagination import PageNumberPagination



class StandardResultsPagination(PageNumberPagination):
    """
    To help us implement pagination

    page_size: 10 // defaults to 10
    max_page_size: 100 // to prevent performance bottle necks we set limit
    page_query_param: page_size // For client to input the numbers they want
    """

    page_size = 10
    page_query_param = 'page_size'
    max_page_size = 100
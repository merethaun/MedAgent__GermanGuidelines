{
retrieval_results = [
    {
        'heading_path': ' / '.join([entry.title for entry in (ref.document_hierarchy or []) if entry.title]),
        'content': ref.extract_content()
    }
    for ref in merge.references
]
subqueries = query_aug.subqueries if hasattr(query_aug, 'subqueries') else []
return f'''Question: {start.current_user_input}

Subqueries used for retrieval:
{subqueries}

Retrieved references:
{retrieval_results}'''
}

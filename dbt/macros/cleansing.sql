{#
    Cleansing macros.

    Each macro repairs one class of defect that the landing zone actually
    contains (see src/drakens360/dirty.py for how each is produced). They are
    macros rather than inline SQL for one reason: the rule for "what counts as
    a null" has to be identical in all 167 staging models, or a sentinel that
    is stripped in one table survives in another and the two disagree.
#}


{% macro clean_text(column) %}
    {#-
        Trim, then map the sentinel strings that extracts use in place of NULL
        onto an actual NULL. Case-folded so 'null', 'NULL' and 'Null' are all
        caught. An empty string after trimming is also a null: a space is not
        a value.
    -#}
    nullif(
        case
            when upper(trim(cast({{ column }} as varchar))) in
                 ('', 'NULL', 'N/A', '#N/A', '-', '?', 'UNKNOWN', 'NONE', 'NA')
                then null
            else trim(cast({{ column }} as varchar))
        end,
        ''
    )
{% endmacro %}


{% macro clean_code(column) %}
    {#-
        Codes additionally get case-folded. ' s000123 ' and 'S000123' are the
        same site; left as-is they produce a silent join miss, which shows up
        as an unexplained gap in a report rather than as an error.
    -#}
    upper({{ clean_text(column) }})
{% endmacro %}


{% macro clean_numeric(column) %}
    {#-
        Parse a number that arrived as text from a flat-file extract.

        Three things have to be undone, in order:
          1. Thousands separators  '1,234.56' -> '1234.56'
          2. Locale decimal comma  '1234,56'  -> '1234.56'
          3. Embedded spaces       '1 234.56' -> '1234.56'

        Distinguishing (1) from (2) is the whole difficulty: a bare comma is
        ambiguous. The rule used here is positional and is what a European
        extract actually means -- if the string contains both a comma and a
        dot, the comma is a thousands separator; if it contains only a comma,
        it is the decimal mark.

        try_cast rather than cast: an unparseable value becomes NULL and is
        caught by the not-null check downstream, instead of failing the whole
        run on one bad row.
    -#}
    try_cast(
        case
            when {{ clean_text(column) }} is null then null
            when {{ clean_text(column) }} like '%.%' and {{ clean_text(column) }} like '%,%'
                then replace(replace({{ clean_text(column) }}, ',', ''), ' ', '')
            when {{ clean_text(column) }} like '%,%'
                then replace(replace({{ clean_text(column) }}, ' ', ''), ',', '.')
            else replace({{ clean_text(column) }}, ' ', '')
        end
        as double
    )
{% endmacro %}


{% macro strip_numeric_sentinels(expression) %}
    {#-
        -999 and friends are 'no reading', not a measurement. Left in place
        they drag averages down by an amount nobody can explain.
    -#}
    case
        when {{ expression }} in (-999, -9999, 999999999) then null
        else {{ expression }}
    end
{% endmacro %}


{% macro clean_measure(column) %}
    {#- The full numeric pipeline: parse, then discard sentinels. -#}
    {{ strip_numeric_sentinels(clean_numeric(column)) }}
{% endmacro %}


{% macro clean_integer(column) %}
    cast({{ strip_numeric_sentinels(clean_numeric(column)) }} as bigint)
{% endmacro %}


{% macro clean_timestamp(column, lower_bound='2023-01-01', upper_bound='2027-12-31') %}
    {#-
        A device with a dead clock reports 1970-01-01; skewed the other way it
        reports 2099. Both are outside any period this business trades in, so
        they are nulled rather than kept: a transaction dated 2099 silently
        breaks every period comparison it lands in.
    -#}
    case
        when try_cast({{ column }} as timestamp) is null then null
        when try_cast({{ column }} as timestamp)
             < cast('{{ lower_bound }}' as timestamp) then null
        when try_cast({{ column }} as timestamp)
             > cast('{{ upper_bound }}' as timestamp) then null
        else try_cast({{ column }} as timestamp)
    end
{% endmacro %}


{% macro fix_mojibake(column) %}
    {#-
        Repair the specific sequences produced when a UTF-8 payload is read as
        Latin-1. Only the known cases are corrected; a general re-decode is not
        possible in SQL, so anything else is left for the quarantine rule to
        catch rather than silently mangled further.
    -#}
    replace(replace(replace(replace(replace(
        {{ clean_text(column) }},
        'GqeberhaÂ', 'Gqeberha'),
        'MbombelaÂ', 'Mbombela'),
        'eMalahleniÃ‚', 'eMalahleni'),
        'CÃ´te', 'Cote'),
        'RÃ©union', 'Reunion')
{% endmacro %}


{% macro correct_unit_error(column, plausible_max) %}
    {#-
        A kilolitre value typed into a litres field is exactly 1000x too large
        and is recoverable, unlike a truly corrupt number. Correcting it is a
        judgement call, so the correction is flagged on the row rather than
        applied silently -- see the `_dq_unit_corrected` column in staging.
    -#}
    case
        when {{ column }} > {{ plausible_max }}
             and {{ column }} / 1000.0 <= {{ plausible_max }}
            then {{ column }} / 1000.0
        else {{ column }}
    end
{% endmacro %}


{% macro cleansing_layer_columns() %}
    {#- Audit columns every cleansed row carries. -#}
    cast('{{ invocation_id }}' as varchar) as _dbt_run_id,
    {{ dbt_load_timestamp() }} as _cleansed_at
{% endmacro %}

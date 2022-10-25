"""Create a feature set for machine learning.
Identify and munge a set of features from the files generated by the prealn-wf
and aln-wf.
Features include:
* CollectRNASeqMetrics
    * PCT_CODING_BASES
    * PCT_UTR_BASES
    * PCT_INTRONIC_BASES
    * PCT_INTERGENIC_BASES
    * PCT_MRNA_BASES
    * MEDIAN_CV_COVERAGE
    * MEDIAN_5PRIME_BIAS
    * MEDIAN_3PRIME_BIAS
* CollectRNASeqMetrics Gene Body Coverage
* Markduplicates
    * PERCENT_DUPLICATION
* Fastq Screen
    * Percent reads mapping to rRNA.
* FeatureCounts
    * Number of reads mapping to junction
"""
from pathlib import Path
from multiprocessing import Pool
import os, argparse
import pandas as pd

THREADS = 3

# NOTE: features commented out are being dropped because they are repetitive or not important.
FEATURE_AGG = {
    "rRNA_pct_reads_mapped": "mean",
    "too_short": "sum",
    "num_reads": "sum",
    "num_multimappers": "sum",
    "per_alignment": "mean",
    "reads_MQ0": "sum",
    "average_quality": "mean",
    "Percent Reverse": "mean",
    "percent_utr_bases": "mean",  # Exclusive of percent_coding and correlated with percent_mrna
    "percent_intronic_bases": "mean",
    "percent_intergenic_bases": "mean",
    "percent_mrna_bases": "mean",
    "median_cv_coverage": "mean",
    "percent_duplication": "mean",
    "number_genic_reads": "sum",
    "percent_genes_on": "mean",
    "number_junction_reads": "sum",
    "number_junctions_on": "sum",
    "gene_body_five_prime": "mean",
    "gene_body_middle": "mean",
    "gene_body_three_prime": "mean",
}

FEATURE_RENAME = {
    "rRNA_pct_reads_mapped": "percent_rrna_reads",
    "too_short": "number_reads_too_short",
    "num_reads": "number_reads",
    "num_multimappers": "number_multimapping_reads",
    "per_alignment": "percent_alignment",
    "Percent Reverse": "percent_reverse",
}


def build_features(input: str, Features: Path):
    feature_dict = {
        "layout": Features / "layout.parquet",
        "fastq_screen": Features / "fastq_screen.parquet",
        "atropos": Features / "atropos.parquet",
        "hisat2": Features / "hisat2.parquet",
        "aln_stats": Features / "aln_stats.parquet",
        "rnaseqmetrics": Features / "rnaseqmetrics.parquet",
        "genebody_coverage": Features / "genebody_coverage.parquet",
        "markduplicates": Features / "markduplicates.parquet",
        "count_summary": Features / "count_summary.parquet"
    }
    done_sample_file = Features / "done_sample.txt"
    # srx2srr = pd.read_csv(input, usecols=["srx", "srr"])
    srr_df = pd.read_table(input)
    if len(srr_df.columns) == 1:
        # only have srr column
        srr_df.columns = ["srr"]
    elif len(srr_df.columns) == 2:
        # have srx and srr column
        srr_df.columns = ["srx", "srr"]
    srr_df = srr_df.set_index("srr", drop=False)
    done_sample_df = pd.read_table(done_sample_file)
    done_srrs = done_sample_df["srr"].values.tolist()
    if len(srr_df.columns) == 2:
        (
            workflow_data(done_srrs, feature_dict)
                .join(srr_df)
                .pipe(aggregate_gene_body_coverage)
                .groupby("srx")
                .agg(FEATURE_AGG)
                .rename(columns=FEATURE_RENAME)
                .to_parquet(Features / "features.parquet")
        )
    else:
        (
            workflow_data(done_srrs, feature_dict)
                .join(srr_df)
                .pipe(aggregate_gene_body_coverage)
                .loc[:, FEATURE_AGG.keys()]
                .rename(columns=FEATURE_RENAME)
                .to_parquet(Features / "features.parquet")
        )


def workflow_data(srrs: list, workflow_folders: dict) -> pd.DataFrame:
    pool = Pool(THREADS)
    df = (
        pd.concat(
            pool.map(pd.read_parquet, [path for _, path in workflow_folders.items()]),
            axis=1,
            sort=False,
        )
            .rename_axis("srr")
            .reindex(srrs)
    )
    pool.close()

    return df


def aggregate_gene_body_coverage(df: pd.DataFrame) -> pd.DataFrame:
    """Sum gene body coverage to tertile.
    GBC is reported as a centile, with positions next to each other being
    highly correlated. For machine learning, I am aggregating these features
    into a tertiles (i.e., 5', middle, 3').
    """
    cols = [f"pos_{i}" for i in range(101)]
    five_prime, middle, three_prime = cols[:33], cols[33:68], cols[68:]
    return (
        df.assign(gene_body_five_prime=lambda x: x[five_prime].sum(axis=1))
            .assign(gene_body_middle=lambda x: x[middle].sum(axis=1))
            .assign(gene_body_three_prime=lambda x: x[three_prime].sum(axis=1))
            .drop(cols, axis=1)
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--input', required=True, type=str,
                        help='Input file, containing two columns srx and srr')
    parser.add_argument('-o', '--outdir', required=True, type=str,
                        help="Path to result output directory of main process.")
    args = parser.parse_args()
    Features = Path(args.outdir) / "Features"
    build_features(args.input, Features)

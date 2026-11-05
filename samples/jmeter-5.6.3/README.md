# Reference run from a real JMeter 5.6.3

Not produced by this project's code, so tests against it prove compatibility.

- `plan.jmx` - 5 labels with 5, 7, 9, 11 and 13 samples (odd on purpose: the median and
  percentiles round differently there). Samples are Groovy sleeps on localhost, no real data.
- `odd_counts.jtl` - the result of `jmeter -n -t plan.jmx -l odd_counts.jtl` (JMeter 5.6.3, CSV).
- `expected_statcalculator.tsv` - the same JTL fed to JMeter's own
  `org.apache.jorphan.math.StatCalculatorLong` (the class behind the Aggregate Report) by
  `Calc.java`: javac -cp "apache-jmeter-5.6.3/lib/*" Calc.java && java -cp ".:apache-jmeter-5.6.3/lib/*" Calc odd_counts.jtl
- `dashboard_statistics.json` - `jmeter -g odd_counts.jtl -o dash`, file `statistics.json`.
  The HTML dashboard computes p90/p95/p99 with interpolation (values like 77.4), a different
  method from the Aggregate Report, so only count, errors, mean, median, min and max are
  compared with it.

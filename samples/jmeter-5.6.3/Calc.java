import org.apache.jorphan.math.StatCalculatorLong;
import java.nio.file.*;
import java.util.*;

/** Feeds the elapsed column of a JTL into JMeter's own StatCalculator (Aggregate Report). */
public class Calc {
    public static void main(String[] args) throws Exception {
        List<String> lines = Files.readAllLines(Paths.get(args[0]));
        Map<String, StatCalculatorLong> per = new LinkedHashMap<>();
        StatCalculatorLong total = new StatCalculatorLong();
        for (String line : lines.subList(1, lines.size())) {
            String[] f = line.split(",", -1);
            long elapsed = Long.parseLong(f[1]);
            per.computeIfAbsent(f[2], k -> new StatCalculatorLong()).addValue(elapsed);
            total.addValue(elapsed);
        }
        System.out.println("label\tsamples\tmean\tmedian\tp90\tp95\tp99\tmin\tmax");
        for (Map.Entry<String, StatCalculatorLong> e : per.entrySet()) row(e.getKey(), e.getValue());
        row("TOTAL", total);
    }
    static void row(String label, StatCalculatorLong c) {
        System.out.println(label + "\t" + c.getCount() + "\t" + (long) c.getMean() + "\t"
            + c.getMedian() + "\t" + c.getPercentPoint(0.90) + "\t" + c.getPercentPoint(0.95)
            + "\t" + c.getPercentPoint(0.99) + "\t" + c.getMin() + "\t" + c.getMax());
    }
}

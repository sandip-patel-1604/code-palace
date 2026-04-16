import java.util.List;
import java.util.ArrayList;

public class App {
    private static final String VERSION = "1.0.0";
    public static final int MAX_SIZE = 256;

    public static void main(String[] args) {
        System.out.println("Code Palace Java sample");
    }

    public String getVersion() {
        return VERSION;
    }

    private void internalSetup() {
        // internal only
    }
}

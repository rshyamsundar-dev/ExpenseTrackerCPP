#include <algorithm>
#include <cctype>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <sstream>
#include <string>
#include <vector>

namespace et {

struct Date { int y{1970}, m{1}, d{1}; };

constexpr bool is_leap(int y) noexcept {
    return (y % 4 == 0 && y % 100 != 0) || (y % 400 == 0);
}
inline bool valid_date(const Date& dt) noexcept {
    if (dt.y < 1900 || dt.m < 1 || dt.m > 12 || dt.d < 1) return false;
    constexpr int md[12] = {31,28,31,30,31,30,31,31,30,31,30,31};
    int days = md[dt.m-1] + ((dt.m==2 && is_leap(dt.y)) ? 1 : 0);
    return dt.d <= days;
}
inline std::optional<Date> parse_date(const std::string& s) {
    if (s.size()!=10 || s[4]!='-' || s[7]!='-') return std::nullopt;
    Date dt{};
    try {
        dt.y = std::stoi(s.substr(0,4));
        dt.m = std::stoi(s.substr(5,2));
        dt.d = std::stoi(s.substr(8,2));
    } catch (...) { return std::nullopt; }
    return valid_date(dt) ? std::optional<Date>(dt) : std::nullopt;
}
inline std::string to_string(const Date& dt) {
    std::ostringstream os;
    os << std::setw(4) << std::setfill('0') << dt.y << "-"
       << std::setw(2) << std::setfill('0') << dt.m << "-"
       << std::setw(2) << std::setfill('0') << dt.d;
    return os.str();
}
constexpr bool date_le(const Date& a, const Date& b) noexcept {
    return (a.y < b.y) || (a.y == b.y && (a.m < b.m || (a.m == b.m && a.d <= b.d)));
}

inline std::string to_lower(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(),
                   [](unsigned char c){ return static_cast<char>(std::tolower(c)); });
    return s;
}
inline bool iequals(const std::string& a, const std::string& b) {
    return to_lower(a) == to_lower(b);
}
inline bool icontains(const std::string& hay, const std::string& needle) {
    auto H = to_lower(hay), N = to_lower(needle);
    return H.find(N) != std::string::npos;
}

// CSV helpers
inline std::string csv_escape(const std::string& s) {
    if (s.find_first_of(",\"\n") == std::string::npos) return s;
    std::string out; out.reserve(s.size()+2); out.push_back('"');
    for (char c : s) { if (c=='"') out.push_back('"'); out.push_back(c); }
    out.push_back('"'); return out;
}
inline std::string csv_unescape(std::string s) {
    if (s.size()>=2 && s.front()=='"' && s.back()=='"') {
        s = s.substr(1, s.size()-2);
        std::string out; out.reserve(s.size());
        for (std::size_t i=0;i<s.size();++i) {
            if (s[i]=='"' && i+1<s.size() && s[i+1]=='"') { out.push_back('"'); ++i; }
            else out.push_back(s[i]);
        }
        return out;
    }
    return s;
}
inline void csv_split_line(const std::string& line, std::vector<std::string>& cols) {
    cols.clear();
    std::string cur; bool in_q=false;
    for (char c : line) {
        if (c=='"') { in_q=!in_q; cur.push_back(c); }
        else if (c==',' && !in_q) { cols.push_back(cur); cur.clear(); }
        else cur.push_back(c);
    }
    cols.push_back(cur);
    for (auto& s : cols) while (!s.empty() && (s.back()=='\r'||s.back()=='\n')) s.pop_back();
}

struct Expense {
    Date date{};
    double amount{0.0};
    std::string category;
    std::string description;
};

class ExpenseManager {
public:
    void add(const Expense& e) { expenses_.push_back(e); } 

    std::vector<Expense> all() const { return expenses_; }

    std::vector<Expense> filter_by_date_range(const Date& from, const Date& to) const {
        std::vector<Expense> out;
        for (const auto& e : expenses_) if (date_le(from,e.date) && date_le(e.date,to)) out.push_back(e);
        return out;
    }
    std::vector<Expense> filter_by_category(const std::string& cat) const {
        std::vector<Expense> out;
        for (const auto& e : expenses_) if (iequals(e.category, cat)) out.push_back(e);
        return out;
    }
    std::vector<Expense> search(const std::string& q) const {
        std::vector<Expense> out;
        for (const auto& e : expenses_) if (icontains(e.category,q) || icontains(e.description,q)) out.push_back(e);
        return out;
    }

    double total(const std::vector<Expense>& list) const {
        double s=0.0; for (const auto& e : list) s += e.amount; return s;
    }
    std::map<std::string,double> totals_by_category(const std::vector<Expense>& list) const {
        std::map<std::string,double> m;
        for (const auto& e : list) m[to_lower(e.category)] += e.amount;
        return m;
    }

    // Optional persistence
    bool save_csv(const std::string& path) const {
        std::ofstream f(path); if (!f) return false;
        f << "date,amount,category,description\n";
        for (const auto& e : expenses_) {
            f << to_string(e.date) << ',' << e.amount << ','
              << csv_escape(e.category) << ',' << csv_escape(e.description) << '\n';
        }
        return true;
    }
    bool load_csv(const std::string& path) {
        std::ifstream f(path); if (!f) return false;
        std::string line; expenses_.clear();
        if (std::getline(f,line)) {
            if (line.rfind("date,amount,category,description",0)!=0) parse_csv_line(line);
        }
        while (std::getline(f,line)) parse_csv_line(line);
        return true;
    }

private:
    std::vector<Expense> expenses_;

    void parse_csv_line(const std::string& line) {
        std::vector<std::string> cols; csv_split_line(line, cols);
        if (cols.size() < 4) return;
        auto d = parse_date(cols[0]); if (!d) return;
        double amt=0.0; try { amt = std::stod(cols[1]); } catch (...) { return; }
        Expense e{ *d, amt, csv_unescape(cols[2]), csv_unescape(cols[3]) };
        expenses_.push_back(std::move(e));
    }
};

// ---- UI helpers ----
inline void print_header() {
    std::cout << " ID  | Date       |     Amount | Category     | Description\n";
    std::cout << "-----+------------+------------+--------------+-------------------------\n";
}
inline void print_row(const Expense& e, std::size_t idx) {
    std::cout << std::setw(4) << idx << " | " << to_string(e.date)
              << " | " << std::fixed << std::setprecision(2) << std::setw(10) << e.amount
              << " | " << std::setw(12) << e.category
              << " | " << e.description << '\n';
}
inline std::string prompt_line(const std::string& label) {
    std::cout << label; std::string s; std::getline(std::cin, s); return s;
}
inline Date prompt_date(const std::string& label) {
    std::cout << label << " (YYYY-MM-DD): ";
    while (true) { std::string s; std::getline(std::cin, s); auto d = parse_date(s); if (d) return *d; std::cout << "Invalid date. Try again: "; }
}
inline Expense prompt_expense() {
    Expense e;
    std::cout << "Enter date (YYYY-MM-DD): ";
    while (true) { std::string ds; std::getline(std::cin, ds); auto d=parse_date(ds); if (d) { e.date=*d; break; } std::cout << "Invalid date. Try again (YYYY-MM-DD): "; }
    std::cout << "Enter amount: ";
    while (true) { std::string s; std::getline(std::cin, s); try { e.amount=std::stod(s); if (e.amount>=0) break; } catch (...) {} std::cout << "Invalid amount. Try again: "; }
    std::cout << "Enter category (e.g., Food, Rent, Travel): "; std::getline(std::cin, e.category); if (e.category.empty()) e.category = "Uncategorized";
    std::cout << "Enter description: "; std::getline(std::cin, e.description);
    return e;
}

} // namespace et

int main() {
    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);

    et::ExpenseManager mgr; 

    while (true) {
        std::cout << "\n==== Expense Tracker (C++) ====\n"
                  << "1) Add expense\n"
                  << "2) View all\n"
                  << "3) Filter by date range\n"
                  << "4) Filter by category\n"
                  << "5) Search (category/description)\n"
                  << "6) Summary (totals by category & overall)\n"
                  << "7) Save to CSV\n"
                  << "8) Load from CSV\n"
                  << "9) Quit\n"
                  << "Choose: ";
        std::string ch; std::getline(std::cin, ch);

        if (ch=="1") {
            auto e = et::prompt_expense(); mgr.add(e); std::cout << "Added.\n";
        } else if (ch=="2") {
            auto list = mgr.all(); et::print_header();
            for (std::size_t i=0;i<list.size();++i) et::print_row(list[i], i);
            std::cout << "Total: " << std::fixed << std::setprecision(2) << mgr.total(list) << '\n';
        } else if (ch=="3") {
            et::Date from = et::prompt_date("From"), to = et::prompt_date("To");
            if (!et::date_le(from, to)) { std::cout << "From must be <= To.\n"; continue; }
            auto list = mgr.filter_by_date_range(from, to); et::print_header();
            for (std::size_t i=0;i<list.size();++i) et::print_row(list[i], i);
            std::cout << "Range total: " << std::fixed << std::setprecision(2) << mgr.total(list) << '\n';
        } else if (ch=="4") {
            std::string cat = et::prompt_line("Category: ");
            auto list = mgr.filter_by_category(cat); et::print_header();
            for (std::size_t i=0;i<list.size();++i) et::print_row(list[i], i);
            std::cout << "Category total: " << std::fixed << std::setprecision(2) << mgr.total(list) << '\n';
        } else if (ch=="5") {
            std::string q = et::prompt_line("Search text: ");
            auto list = mgr.search(q); et::print_header();
            for (std::size_t i=0;i<list.size();++i) et::print_row(list[i], i);
            std::cout << "Search total: " << std::fixed << std::setprecision(2) << mgr.total(list) << '\n';
        } else if (ch=="6") {
            auto list = mgr.all(); auto by = mgr.totals_by_category(list);
            std::cout << "Totals by category:\n";
            for (const auto& kv : by) {
                std::cout << "  " << std::setw(12) << std::left << kv.first << " : "
                          << std::fixed << std::setprecision(2) << kv.second << '\n';
            }
            std::cout << "Overall total: " << std::fixed << std::setprecision(2) << mgr.total(list) << '\n';
        } else if (ch=="7") {
            std::string path = et::prompt_line("Save CSV path (e.g., expenses.csv): ");
            std::cout << (mgr.save_csv(path) ? "Saved.\n" : "Failed to save.\n");
        } else if (ch=="8") {
            std::string path = et::prompt_line("Load CSV path: ");
            std::cout << (mgr.load_csv(path) ? "Loaded.\n" : "Failed to load.\n");
        } else if (ch=="9" || ch=="q" || ch=="Q") {
            std::cout << "Bye!\n"; break;
        } else {
            std::cout << "Invalid choice.\n";
        }
    }
    return 0;
}

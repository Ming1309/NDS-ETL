## 0. Hướng Dẫn Sử Dụng & Vận Hành

### Cập nhật Cookie phiên làm việc

Khi phiên đăng nhập hoặc cookie của Agoda hết hạn, cập nhật chuỗi cookie mới tại hằng số `COOKIE_STRING` trong file [agoda_config.py].

Vào 1 trang chi tiết 1 khách sạn -> Bật Inspect -> Qua Network -> Bật Fetch/XHR -> Reload -> Kiếm 'property' -> Chuột trái -> Chọn Copy as cURL (bash) -> Đưa cho AI kêu nó điền vào agoda_config.py

### Lệnh chạy thu thập dữ liệu

```bash
# Di chuyển vào thư mục dự án
cd <thư mục>

# Cách 1: Chạy trọn gói từ A-Z (Cào danh sách mới + bóc tách toàn bộ 5 file chi tiết):
python run_all_crawlers.py --all

# Cách 2: Đã có sẵn hotels_cleaned.json, chỉ cần bóc tách đồng loạt 5 file chi tiết:
python run_all_crawlers.py

# Cách 3: Chạy riêng lẻ từng crawler khi cần debug hoặc cập nhật từng phần:
python hotel_profile_crawler.py
python hotel_review_scores_crawler.py
python AI_review_tags_summary.py
python hotel_facilities_highlights_crawler.py
python hotel_nearby_places_crawler.py
```

> **Lưu ý định dạng xuất file:**
>
> - Toàn bộ các file `.csv` đi kèm đều được lưu với mã hóa chuẩn `utf-8-sig` (UTF-8 with BOM), tương thích tuyệt đối khi mở trực tiếp bằng Microsoft Excel trên Windows mà không bị lỗi ký tự tiếng Việt.

> - Data được lấy từ 11 nơi trên Việt Nam hay được khách du lịch chọn đi nhất (AgodaTopDestinationsDemo.json), do Agoda không có AI hay bất cứ source nào để lấy full list các địa điểm ở Việt Nam mà họ có

> - Data được bóc tách từ việc phân tích thông tin của 1 khách sạn demo trong AgodaHotelDetailDemo.json

---

## 1. Sơ Đồ Trực quan

- Ảnh Agoda_tables_info.drawio.png (Ảnh nội dung từng file json/csv đc hiển thị dạng bảng giống ERD)
- Ảnh Agoda_datacrawling_flow.drawio.png (Ảnh flow các file được tạo lần lượt khi chạy run_all_crawlers.py)

---

## 2. Mô Tả Chi Tiết Từng File JSON & Ý Nghĩa Thuộc Tính

---

### 2.1. `hotels_cleaned.json` (Master Discovery Dataset)

- **Tập tin nguồn gốc**: Được tạo bởi [agoda_crawler.py]
- **Mục đích**: Chứa danh sách khách sạn thu thập được từ trang tìm kiếm (Search Results page) qua các thành phố du lịch lớn. Đây là danh mục cơ sở (Master Key List) cung cấp `property_id` cho các crawler chi tiết khác.

| Tên thuộc tính         | Kiểu dữ liệu   | Mô tả chi tiết                                                                        |
| :--------------------- | :------------- | :------------------------------------------------------------------------------------ |
| `property_id`          | `int`          | Mã số định danh duy nhất của khách sạn trên Agoda (**Primary Key**).                  |
| `name`                 | `str`          | Tên thương mại đầy đủ của khách sạn hiển thị cho người dùng.                          |
| `stars`                | `float`        | Xếp hạng số sao tiêu chuẩn của khách sạn (từ 1.0 đến 5.0).                            |
| `accommodation_type`   | `int`          | Mã phân loại hình thức lưu trú nội bộ của Agoda (Ví dụ: `34` = Hotel).                |
| `property_type`        | `str`          | Tên hình thức lưu trú bằng chữ (Ví dụ: `Hotel`, `Resort`, `Serviced Apartment`).      |
| `city`                 | `str`          | Tên thành phố / điểm đến du lịch (Ví dụ: `Ho Chi Minh City`, `Da Nang`).              |
| `area`                 | `str`          | Tên quận huyện hoặc khu vực cụ thể (Ví dụ: `District 1`, `Phước Mỹ`).                 |
| `average_price_vnd`    | `int`          | Giá phòng trung bình mỗi đêm (đã quy đổi sang VNĐ, tính theo phiên).                  |
| `review_score`         | `float`        | Điểm số đánh giá trung bình hiển thị ngoài trang kết quả tìm kiếm.                    |
| `review_count`         | `int`          | Tổng số lượt khách đã gửi nhận xét đánh giá.                                          |
| `recommendation_score` | `int` / `null` | Tỉ lệ phần trăm khách hàng khuyên nên ở đây.                                          |
| `customer_reviews`     | `str`          | Chuỗi ghép mẫu 2-3 câu bình luận tiêu biểu của khách hàng.                            |
| `facilities`           | `str`          | Danh sách các tiện ích tiêu biểu hiển thị dạng chuỗi phân cách bởi dấu chấm phẩy `;`. |
| `hotel_url`            | `str`          | Đường dẫn URL trực tiếp đến trang chi tiết khách sạn trên website Agoda.              |
| `image_url`            | `str`          | Đường dẫn ảnh đại diện (thumbnail) của khách sạn ngoài trang kết quả.                 |

---

### 2.2. `hotel_profile.json` (Hồ Sơ Chi Tiết Khách Sạn)

- **Tập tin nguồn gốc**: Được tạo bởi [hotel_profile_crawler.py]
- **Mục đích**: Lưu trữ thông tin tĩnh chi tiết (Dimension Hotel) về cơ sở vật chất, vị trí địa lý chuẩn, quy mô phòng ốc, chính sách nhận/trả phòng.

| Tên thuộc tính           | Kiểu dữ liệu   | Mô tả chi tiết                                                                   |
| :----------------------- | :------------- | :------------------------------------------------------------------------------- |
| `property_id`            | `int`          | Khóa chính liên kết (**Foreign Key** liên kết với `hotels_cleaned`).             |
| `hotel_name`             | `str`          | Tên khách sạn theo ngôn ngữ hiển thị (tiếng Việt).                               |
| `default_name`           | `str`          | Tên quốc tế / tiếng Anh chuẩn của khách sạn.                                     |
| `property_type`          | `str`          | Loại tài sản lưu trú (Hotel, Resort, Villa...).                                  |
| `accommodation_type`     | `str`          | Tên loại hình lưu trú được chuẩn hóa dạng chữ.                                   |
| `stars`                  | `float`        | Số sao xếp hạng chính thức.                                                      |
| `is_luxury`              | `bool`         | Đánh dấu khách sạn thuộc phân khúc cao cấp/sang trọng (`True`/`False`).          |
| `address_line`           | `str`          | Địa chỉ số nhà, tên đường chi tiết.                                              |
| `area_name`              | `str`          | Tên phường / xã / khu vực hành chính.                                            |
| `area_id`                | `int`          | Mã ID định danh khu vực của Agoda.                                               |
| `city_name`              | `str`          | Tên thành phố trực thuộc.                                                        |
| `city_id`                | `int`          | Mã ID định danh thành phố của Agoda.                                             |
| `country_name`           | `str`          | Tên quốc gia (Ví dụ: `Vietnam`).                                                 |
| `postal_code`            | `str`          | Mã bưu chính của khu vực khách sạn.                                              |
| `latitude`               | `float`        | Tọa độ vĩ độ GPS để hiển thị bản đồ GIS.                                         |
| `longitude`              | `float`        | Tọa độ kinh độ GPS để hiển thị bản đồ GIS.                                       |
| `year_opened`            | `str`          | Năm khai trương mở cửa hoặc năm cải tạo nâng cấp gần nhất.                       |
| `number_of_rooms`        | `str`          | Tổng số lượng phòng kinh doanh trong khách sạn.                                  |
| `number_of_floors`       | `str`          | Tổng số tầng của tòa nhà khách sạn.                                              |
| `check_in_from`          | `str`          | Thời gian bắt đầu cho phép nhận phòng (Ví dụ: `14:00`, `12:00`).                 |
| `check_out_until`        | `str`          | Thời hạn tối đa phải trả phòng (Ví dụ: `12:00`).                                 |
| `breakfast_charge`       | `str`          | Mức phí ăn sáng nếu không đi kèm trong gói đặt phòng (Ví dụ: `400000 VND`).      |
| `airport_transfer_fee`   | `str`          | Chi phí dịch vụ đưa đón sân bay từ khách sạn.                                    |
| `gold_circle_award_year` | `str`          | Năm khách sạn đạt giải thưởng dịch vụ xuất sắc Agoda Gold Circle Award.          |
| `today_booking`          | `str`          | Thông báo tần suất đặt phòng thực tế trong ngày (Ví dụ: `Booked 5 times today`). |
| `booking_count_last_24h` | `int` / `null` | Số lượng giao dịch đặt phòng thành công trong 24 giờ qua.                        |
| `recommendation_score`   | `int` / `null` | Điểm chỉ số đề xuất của khách lưu trú.                                           |
| `main_image_url`         | `str`          | URL ảnh chất lượng cao chụp toàn cảnh mặt tiền khách sạn.                        |

---

### 2.3. `hotel_review_scores.json` (Bảng Điểm Đánh Giá & Trích Dẫn Thực Tế)

- **Tập tin nguồn gốc**: Được tạo bởi [hotel_review_scores_crawler.py]
- **Mục đích**: Đóng vai trò Fact Metrics đo lường mức độ hài lòng của khách hàng: điểm số tích lũy, 5 điểm thành phần và trích xuất nguyên văn phản hồi của du khách.

| Tên thuộc tính            | Kiểu dữ liệu | Mô tả chi tiết                                                          |
| :------------------------ | :----------- | :---------------------------------------------------------------------- |
| `property_id`             | `int`        | Khóa chính liên kết (**Foreign Key** liên kết với `hotels_cleaned`).    |
| `overall_score`           | `float`      | Điểm đánh giá trung bình tổng thể của khách sạn (thang điểm 10).        |
| `review_count`            | `int`        | Tổng số lượng bài nhận xét đánh giá được ghi nhận.                      |
| `score_cleanliness`       | `float`      | Điểm số tiêu chí con: **Độ sạch sẽ** của phòng và khuôn viên.           |
| `score_facilities`        | `float`      | Điểm số tiêu chí con: **Chất lượng tiện nghi** và cơ sở vật chất.       |
| `score_location`          | `float`      | Điểm số tiêu chí con: **Vị trí** và sự thuận tiện di chuyển.            |
| `score_staff`             | `float`      | Điểm số tiêu chí con: **Thái độ và sự hỗ trợ của nhân viên**.           |
| `score_value_for_money`   | `float`      | Điểm số tiêu chí con: **Mức độ tương xứng với số tiền bỏ ra**.          |
| `count_exceptional`       | `int`        | Số lượng khách chấm điểm xếp hạng: **Tuyệt đỉnh** (Điểm từ 9.0 - 10.0). |
| `count_excellent`         | `int`        | Số lượng khách chấm điểm xếp hạng: **Xuất sắc** (Điểm từ 8.0 - 8.9).    |
| `count_very_good`         | `int`        | Số lượng khách chấm điểm xếp hạng: **Rất tốt** (Điểm từ 7.0 - 7.9).     |
| `count_good`              | `int`        | Số lượng khách chấm điểm xếp hạng: **Tốt** (Điểm từ 6.0 - 6.9).         |
| `count_below_expectation` | `int`        | Số lượng khách chấm điểm: **Dưới kỳ vọng** (Điểm dưới 6.0).             |
| `sample_customer_reviews` | `str`        | Chuỗi văn bản trích dẫn mẫu đánh giá ngắn kèm điểm số và tên du khách.  |
| `snippets_detail`         | `list[dict]` | Mảng JSON chứa chi tiết từng bài đánh giá thực tế bóc tách từ Agoda.    |

#### Cấu trúc mỗi phần tử trong mảng `snippets_detail`:

```json
{
  "snippet_id": 163208783800,
  "reviewer": "REVATHY",
  "rating": 10.0,
  "country": "Malaysia",
  "demographic": "Couple",
  "date": "2026-03-01",
  "text": "The hotel features everything you need for a seamless stay. Rooms are modern and spotless."
}
```

---

### 2.4. `AI_review_tags_summary.json` (AI Aspect-Based Sentiment & Tags)

- **Tập tin nguồn gốc**: Được tạo bởi [AI_review_tags_summary.py]
- **Mục đích**: Lưu trữ kết quả phân tích xử lý ngôn ngữ tự nhiên (NLP) do AI của Agoda tổng hợp từ hàng ngàn bình luận của khách để rút trích khía cạnh (Aspect-Based Sentiment).

| Tên thuộc tính        | Kiểu dữ liệu | Mô tả chi tiết                                                                 |
| :-------------------- | :----------- | :----------------------------------------------------------------------------- |
| `property_id`         | `int`        | Khóa chính liên kết (**Foreign Key** liên kết với `hotels_cleaned`).           |
| `ai_positive_summary` | `str`        | Đoạn văn do mô hình AI tổng hợp những điểm được du khách khen ngợi nhiều nhất. |
| `ai_negative_summary` | `str`        | Đoạn văn do mô hình AI tổng hợp những điểm du khách phàn nàn cần cải thiện.    |
| `total_tags`          | `int`        | Tổng số lượng tag chủ đề AI bóc tách được cho khách sạn này.                   |
| `review_tags`         | `list[dict]` | Mảng danh sách các nhãn khía cạnh kèm định lượng độ hài lòng.                  |

#### Cấu trúc mỗi phần tử trong mảng `review_tags`:

```json
{
  "tag_id": 1,
  "tag_name": "service",
  "positive_percentage": 0.9353,
  "rating_type": "POSITIVE"
}
```

- `tag_name`: Chủ đề khía cạnh (Ví dụ: `service`, `breakfast`, `room`, `cleanliness`, `location`, `view`).
- `positive_percentage`: Tỉ lệ khách đánh giá tích cực cho khía cạnh này (từ `0.0` đến `1.0`, ví dụ `0.9353` = 93.53% khen).
- `rating_type`: Phân loại cảm xúc (`POSITIVE`, `NEGATIVE`, `NEUTRAL`).

---

### 2.5. `hotel_facilities_highlights.json` (Tiện Nghi & Điểm Nhấn)

- **Tập tin nguồn gốc**: Được tạo bởi [hotel_facilities_highlights_crawler.py]
- **Mục đích**: Quản lý danh mục cơ sở vật chất, phân loại theo từng nhóm tiện ích và các tiện ích quan trọng hàng đầu (Above-The-Fold Highlights).

| Tên thuộc tính         | Kiểu dữ liệu | Mô tả chi tiết                                                          |
| :--------------------- | :----------- | :---------------------------------------------------------------------- |
| `property_id`          | `int`        | Khóa chính liên kết (**Foreign Key** liên kết với `hotels_cleaned`).    |
| `total_highlights`     | `int`        | Tổng số lượng tiện ích được đánh dấu là nổi bật nhất.                   |
| `highlights`           | `list[dict]` | Mảng các tiện ích cốt lõi hiển thị ngay đầu trang (Above-The-Fold).     |
| `total_feature_groups` | `int`        | Tổng số danh mục nhóm tiện ích mà khách sạn cung cấp.                   |
| `feature_groups`       | `list[dict]` | Mảng danh sách phân cấp gồm tên nhóm và tất cả tính năng thuộc nhóm đó. |

#### Cấu trúc mỗi phần tử trong mảng `highlights`:

```json
{
  "category": "topic-highlight",
  "name": "Great breakfast",
  "symbol": "coffee",
  "tooltip": "Bữa sáng được đánh giá cao bởi khách hàng"
}
```

#### Cấu trúc mỗi phần tử trong mảng `feature_groups`:

```json
{
  "group_name": "Languages spoken",
  "features": ["English", "Vietnamese", "Japanese", "Chinese [Mandarin]"]
}
```

_(Các nhóm phổ biến: An toàn & Vệ sinh, Thể thao & Giải trí, Tiện nghi phòng tắm, Dịch vụ phòng, Tiện ích văn phòng, v.v.)_

---

### 2.6. `hotel_nearby_places.json` (Vị Trí & Địa Điểm Xung Quanh)

- **Tập tin nguồn gốc**: Được tạo bởi [hotel_nearby_places_crawler.py]
- **Mục đích**: Cung cấp thông tin địa lý bán kính xung quanh khách sạn: khoảng cách ra biển, khoảng cách vào trung tâm và danh sách các danh lam thắng cảnh, sân bay, nhà ga lân cận.

| Tên thuộc tính          | Kiểu dữ liệu     | Mô tả chi tiết                                                                                  |
| :---------------------- | :--------------- | :---------------------------------------------------------------------------------------------- |
| `property_id`           | `int`            | Khóa chính liên kết (**Foreign Key** liên kết với `hotels_cleaned`).                            |
| `distance_to_beach_km`  | `float` / `null` | Khoảng cách đường bộ/chim bay ra bờ biển gần nhất (km). Nếu là vùng không có biển sẽ là `null`. |
| `distance_to_center_km` | `float`          | Khoảng cách vào trung tâm hành chính của thành phố (km).                                        |
| `location_subscores`    | `dict`           | Object điểm đánh giá độ tiện lợi của vị trí theo từng tiêu chuẩn:                               |
| ↳ `airport`             | `float`          | Điểm độ thuận tiện khi di chuyển ra sân bay (thang điểm 10).                                    |
| ↳ `poi`                 | `float`          | Điểm độ thuận tiện tới các điểm tham quan / giải trí (Points of Interest).                      |
| ↳ `transportation`      | `float`          | Điểm tiếp cận các phương tiện giao thông công cộng (xe buýt, tàu hỏa).                          |
| `total_nearby_places`   | `int`            | Tổng số lượng địa điểm tham quan lân cận được liệt kê.                                          |
| `nearby_places`         | `list[dict]`     | Mảng chi tiết từng địa điểm xung quanh kèm khoảng cách và thời gian ước lượng.                  |

#### Cấu trúc mỗi phần tử trong mảng `nearby_places`:

```json
{
  "place_name": "The Venerable Thich Quang Duc Monument",
  "place_type": "landmark",
  "distance_km": 0.45,
  "duration_minutes": 6
}
```

---

## 3. Bản Đồ File Mã Nguồn Python (Crawler Modules)

| Tên file Python                          | Chức năng thực hiện                                                      | File đầu ra tương ứng                                                   |
| :--------------------------------------- | :----------------------------------------------------------------------- | :---------------------------------------------------------------------- |
| [agoda_config.py]                        | Cấu hình tập trung: Chứa Cookies, Headers, GraphQL Endpoints dùng chung. | _(Cấu hình)_                                                            |
| [agoda_crawler.py]                       | Cào danh sách khách sạn qua các thành phố du lịch trên Agoda Search.     | `hotels_cleaned.json`<br>`hotels_cleaned.csv`                           |
| [hotel_profile_crawler.py]               | Bóc tách hồ sơ chi tiết, quy mô phòng ốc, năm khánh thành, tọa độ GPS.   | `hotel_profile.json`<br>`hotel_profile.csv`                             |
| [hotel_review_scores_crawler.py]         | Bóc tách điểm số 5 tiêu chí, phân bố xếp loại và trích dẫn bình luận.    | `hotel_review_scores.json`<br>`hotel_review_scores.csv`                 |
| [AI_review_tags_summary.py]              | Bóc tách tóm tắt AI cảm xúc khen/chê và danh sách các tag khía cạnh NLP. | `AI_review_tags_summary.json`<br>`AI_review_tags_summary.csv`           |
| [hotel_facilities_highlights_crawler.py] | Bóc tách tiện nghi nổi bật (ATF) và cây danh mục tiện ích theo nhóm.     | `hotel_facilities_highlights.json`<br>`hotel_facilities_highlights.csv` |
| [hotel_nearby_places_crawler.py]         | Bóc tách khoảng cách ra biển, trung tâm và danh sách địa điểm lân cận.   | `hotel_nearby_places.json`<br>`hotel_nearby_places.csv`                 |
| [run_all_crawlers.py]                    | Bộ điều phối chạy toàn bộ hoặc tùy chọn chạy từng crawler theo tham số.  | _(Điều phối Pipeline)_                                                  |

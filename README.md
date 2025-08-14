# Stock Options Strategy API

A FastAPI-based application that analyzes stocks for bull put credit spread trading opportunities using real-time market data and AI-powered insights.

## 🚀 Features

- **Real-time Stock Analysis**: Fetches live market data using Alpha Vantage API
- **Bull Put Credit Spread Evaluation**: Algorithmic assessment of trading opportunities
- **AI-Powered Insights**: Optional OpenAI integration for market analysis
- **Fast Response Times**: Optimized for speed (~6 seconds response time)
- **Production Ready**: Deployed on AWS ECS Fargate with Application Load Balancer
- **CI/CD Pipeline**: Automated deployment via GitHub Actions

## 📊 API Endpoints

### `GET /`
Health check endpoint returning API information.

### `POST /check-dip`
Analyzes a stock ticker for bull put credit spread opportunities.

**Request Body:**
```json
{
  "ticker": "AAPL",
  "include_ai_analysis": true
}
```

**Response:**
```json
{
  "ticker": "AAPL",
  "play": false,
  "tier": "tier_3",
  "metrics": {
    "current_price": 229.65,
    "RSI": 71.9,
    "percent_drop": -2.3,
    "distance_from_low": 15.2,
    "ma200": 195.45,
    "max_recent_drop": -8.1,
    "rolling_5d_drop": -1.2,
    "rolling_10d_drop": -3.4,
    "days_oversold": 0,
    "price_vs_200ma": 17.5
  },
  "reason": "RSI above 70 (overbought territory)",
  "confidence_score": 0.75,
  "confidence_source": "algorithmic",
  "estimated_credit": 2.45,
  "ai_analysis": {
    "analysis": "AAPL shows strong fundamentals but current RSI suggests overbought conditions...",
    "model": "gpt-4o-mini",
    "confidence": 0.75,
    "timestamp": "2024-08-13T20:30:15.123Z"
  }
}
```

## 🛠️ Technology Stack

- **Backend**: FastAPI (Python 3.11)
- **Data Provider**: Alpha Vantage API
- **AI Integration**: OpenAI GPT-4o-mini
- **Infrastructure**: AWS ECS Fargate, Application Load Balancer
- **Containerization**: Docker
- **CI/CD**: GitHub Actions
- **Infrastructure as Code**: Terraform
- **Secrets Management**: AWS Secrets Manager

## 🏗️ Architecture

```
GitHub → GitHub Actions → ECR → ECS Fargate → ALB → Internet
                                     ↓
                            Secrets Manager (API Keys)
```

- **ECS Fargate**: Serverless container hosting
- **Application Load Balancer**: 5-minute timeout for longer processing
- **Secrets Manager**: Secure storage for Alpha Vantage and OpenAI API keys
- **ECR**: Container image registry

## 🚀 Local Development

### Prerequisites
- Python 3.11+
- Docker
- Alpha Vantage API key
- OpenAI API key (optional)

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-username/stock_options_strategy_api.git
   cd stock_options_strategy_api
   ```

2. **Create environment file**
   ```bash
   cp .env.example .env
   ```
   
   Add your API keys to `.env`:
   ```
   VANTAGE_API_KEY=your_alpha_vantage_key_here
   OPENAI_API_KEY=your_openai_key_here
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run locally**
   ```bash
   uvicorn app:app --host 0.0.0.0 --port 8000 --reload
   ```

5. **Test the API**
   ```bash
   curl -X POST "http://localhost:8000/check-dip" \
     -H "Content-Type: application/json" \
     -d '{"ticker":"AAPL","include_ai_analysis":true}'
   ```

### Docker Development

1. **Build and run with Docker**
   ```bash
   docker build -t stock-options-api .
   docker run -p 8000:8000 --env-file .env stock-options-api
   ```

## 🚀 Deployment

### AWS Infrastructure

The application is deployed using Terraform and includes:

- **ECS Fargate Cluster**: Serverless container hosting
- **Application Load Balancer**: Internet-facing with 5-minute timeout
- **VPC with Public/Private Subnets**: Secure networking
- **NAT Gateway**: Outbound internet access for containers
- **ECR Repository**: Docker image storage
- **Secrets Manager**: Secure API key storage
- **IAM Roles**: Least-privilege access

### Deployment Steps

1. **Configure AWS credentials**
   ```bash
   export AWS_ACCESS_KEY_ID=your_access_key
   export AWS_SECRET_ACCESS_KEY=your_secret_key
   export AWS_SESSION_TOKEN=your_session_token
   export AWS_DEFAULT_REGION=us-west-2
   ```

2. **Deploy infrastructure**
   ```bash
   cd terraform
   terraform init
   terraform apply \
     -var="vantage_api_key=your_key" \
     -var="openai_api_key=your_key"
   ```

3. **Push code to trigger deployment**
   ```bash
   git push origin main
   ```

   GitHub Actions will automatically:
   - Build the Docker image
   - Push to ECR
   - Update ECS service

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `VANTAGE_API_KEY` | Alpha Vantage API key for stock data | Yes |
| `OPENAI_API_KEY` | OpenAI API key for AI analysis | No |

## 📈 Trading Strategy

The API implements a bull put credit spread strategy evaluation based on:

### Technical Indicators
- **RSI (Relative Strength Index)**: Identifies oversold conditions
- **Moving Averages**: 200-day MA for trend analysis
- **Price Action**: Recent drops and support levels
- **Volume Analysis**: Confirms price movements

### Evaluation Criteria
- **Tier 1**: High confidence plays (RSI < 30, significant drop)
- **Tier 2**: Medium confidence plays (RSI 30-40, moderate drop)
- **Tier 3**: Low confidence plays (RSI 40-50, minor drop)
- **No Play**: Unfavorable conditions (RSI > 50 or uptrend)

### Risk Management
- Automatic credit estimation based on volatility
- Confidence scoring (0.0 - 1.0)
- Multiple data source validation

## 🔧 Configuration

### Rate Limiting
Alpha Vantage free tier limits:
- **25 requests per day**
- **5 requests per minute**

The API is optimized to stay within these limits using:
- Efficient data fetching (single request per analysis)
- Response caching
- Error handling for rate limits

### Performance Optimization
- **Docker multi-stage builds**: Smaller image size
- **Single API call per request**: Minimizes external dependencies
- **Async processing**: Non-blocking operations
- **Efficient algorithms**: Fast technical indicator calculations

## 🛡️ Security

- **API keys stored in AWS Secrets Manager**
- **No sensitive data in code or logs**
- **VPC isolation for containers**
- **Security groups restricting access**
- **HTTPS termination at load balancer**

## 📊 Monitoring

- **CloudWatch Logs**: Application and infrastructure logs
- **ECS Service Metrics**: Container health and performance
- **ALB Metrics**: Request/response monitoring
- **Custom metrics**: Trading signal accuracy

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## ⚠️ Disclaimer

This API is for educational and research purposes only. It does not constitute financial advice. Always do your own research and consult with a qualified financial advisor before making trading decisions. Past performance does not guarantee future results.

## 🆘 Support

For support and questions:
- Create an issue in this repository
- Check the documentation
- Review logs in CloudWatch (for production issues)

## 🗺️ Roadmap

- [ ] WebSocket support for real-time updates
- [ ] Additional trading strategies (iron condors, strangles)
- [ ] Backtesting functionality
- [ ] Portfolio tracking
- [ ] Email/SMS alerts
- [ ] Web dashboard interface 
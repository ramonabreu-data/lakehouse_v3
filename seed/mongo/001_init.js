// Use the 'mydatabase' database
db = db.getSiblingDB('mydatabase');

// Create a collection named 'customer_preferences'
db.createCollection('customer_preferences');

// Insert data into the 'customer_preferences' collection
db.customer_preferences.insertMany([
  {
    customer_email: 'johndoe@example.com',
    preference: 'Electronics',
    loyalty_status: 'Gold',
    last_updated: new Date('2024-09-01')
  },
  {
    customer_email: 'janesmith@example.com',
    preference: 'Books',
    loyalty_status: 'Silver',
    last_updated: new Date('2024-09-02')
  },
  {
    customer_email: 'bobjohnson@example.com',
    preference: 'Clothing',
    loyalty_status: 'Bronze',
    last_updated: new Date('2024-09-03')
  }
]);
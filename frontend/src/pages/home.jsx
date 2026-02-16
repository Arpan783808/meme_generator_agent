import React from 'react';
import Terminal from '../components/Terminal';

const Home = () => {
  return (
    <div className="space-background">
      <div className="nebula"></div>
      <div className="stars"></div>
      <div className="stars-sm"></div>
    
      <div className="flex justify-center items-center h-screen relative z-10">
        <Terminal />
      </div>
    </div>
  );
};

export default Home;
